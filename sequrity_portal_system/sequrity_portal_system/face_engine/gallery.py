"""Step 6 - compare a face vector with everyone enrolled. One matrix multiply, so
200 students (or 20,000) take well under a millisecond."""
import numpy as np
from . import config as C


class Gallery:
    def __init__(self):
        self.M = np.zeros((0, 128), dtype=np.float32)
        self.owner = np.zeros((0,), dtype=np.int64)
        self.users = []

    def load(self, rows):
        """rows: iterable of (user_id, vector). A person can have several vectors (several photos)."""
        rows = list(rows)
        if not rows:
            self.__init__()
            return
        self.owner = np.array([r[0] for r in rows], dtype=np.int64)
        self.M = np.stack([np.asarray(r[1], dtype=np.float32) for r in rows])
        self.users = sorted(set(self.owner.tolist()))

    def __len__(self):
        return len(self.users)

    def _per_user(self, sims):
        """best similarity for each enrolled person -> (user_ids, scores)"""
        users = np.array(self.users)
        best = np.full(len(users), -1.0, dtype=np.float32)
        idx = {u: i for i, u in enumerate(self.users)}
        for u_id, s in zip(self.owner, sims):
            i = idx[int(u_id)]
            if s > best[i]:
                best[i] = s
        return users, best

    def identify(self, vec, threshold=C.MATCH_THRESHOLD, margin=C.MATCH_MARGIN, only=None):
        """-> dict(decision, user_id, score, margin). decision: match | uncertain | no_match"""
        if not len(self.owner):
            return dict(decision="no_match", user_id=None, score=0.0, margin=0.0)
        users, best = self._per_user(self.M @ np.asarray(vec, dtype=np.float32))
        if only is not None:
            keep = np.isin(users, list(only))
            users, best = users[keep], best[keep]
            if not len(users):
                return dict(decision="no_match", user_id=None, score=0.0, margin=0.0)
        order = np.argsort(-best)
        top = float(best[order[0]])
        second = float(best[order[1]]) if len(order) > 1 else -1.0
        gap = top - second if second > -1 else 1.0
        uid = int(users[order[0]])
        if top >= threshold and gap >= margin:
            decision = "match"
        elif top >= threshold:
            decision = "uncertain"       # two people look alike: ask for a retake or a manual check
        else:
            decision = "no_match"
        return dict(decision=decision, user_id=uid if decision != "no_match" else None, score=top, margin=float(gap))

    def duplicates(self, vec, exclude_user=None, threshold=C.DUPLICATE_THRESHOLD):
        """Existing accounts whose face is very close to this one (double registration check)."""
        if not len(self.owner):
            return []
        users, best = self._per_user(self.M @ np.asarray(vec, dtype=np.float32))
        return [(int(u), float(s)) for u, s in zip(users, best) if s >= threshold and u != exclude_user]

    def match_group(self, vectors, only=None, threshold=C.GROUP_MATCH_THRESHOLD):
        """Class photo: many faces -> people. Each face and each person is used at most once.
        Returns list of (face_index, user_id, score)."""
        if not len(self.owner) or not len(vectors):
            return []
        F = np.stack(vectors).astype(np.float32)
        S = F @ self.M.T                                  # faces x templates
        users = np.array(self.users)
        P = np.full((len(F), len(users)), -1.0, dtype=np.float32)
        idx = {u: i for i, u in enumerate(self.users)}
        for j, u_id in enumerate(self.owner):
            i = idx[int(u_id)]
            P[:, i] = np.maximum(P[:, i], S[:, j])
        if only is not None:
            P[:, ~np.isin(users, list(only))] = -1.0
        pairs = sorted(((float(P[f, u]), f, u) for f in range(P.shape[0]) for u in range(P.shape[1])), reverse=True)
        used_f, used_u, out = set(), set(), []
        for score, f, u in pairs:
            if score < threshold:
                break
            if f in used_f or u in used_u:
                continue
            used_f.add(f); used_u.add(u)
            out.append((f, int(users[u]), score))
        return out
