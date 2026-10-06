-- Handy queries for reports. Open database/campus.db in "DB Browser for SQLite" or the VS Code "SQLite Viewer" extension.

-- 1. All approved students with overall attendance %
SELECT u.name, s.prn, s.roll_no, u.department, s.year, s.division,
       ROUND(100.0 * SUM(a.present) / COUNT(a.id), 1) AS attendance_pct
FROM users u JOIN students s ON s.user_id = u.id
LEFT JOIN attendance a ON a.student_id = u.id
WHERE u.role = 'student' AND u.status = 'approved'
GROUP BY u.id ORDER BY attendance_pct;

-- 2. Students below 75% in any subject
SELECT u.name, s.prn, sub.name AS subject,
       ROUND(100.0 * SUM(a.present) / COUNT(a.id), 1) AS pct
FROM attendance a
JOIN class_sessions cs ON cs.id = a.session_id
JOIN subjects sub ON sub.id = cs.subject_id
JOIN users u ON u.id = a.student_id
JOIN students s ON s.user_id = u.id
GROUP BY a.student_id, sub.id HAVING pct < 75;

-- 3. Who is on campus right now
SELECT name, role, department, last_seen FROM users WHERE in_campus = 1;

-- 4. Today's gate scans
SELECT sl.created_at, COALESCE(u.name, 'Unknown') AS person, sl.direction, sl.result, ROUND(sl.score, 2) AS score
FROM scan_log sl LEFT JOIN users u ON u.id = sl.matched_user_id
WHERE date(sl.created_at, 'localtime') = date('now', 'localtime') ORDER BY sl.id DESC;

-- 5. Registrations waiting for HOD approval
SELECT u.name, s.prn, s.roll_no, u.department, s.dup_note FROM users u
JOIN students s ON s.user_id = u.id WHERE u.status = 'pending';

-- 6. Number of students per department
SELECT department, COUNT(*) AS students FROM users WHERE role = 'student' AND status = 'approved' GROUP BY department;
