import os
import re
import socket
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

class DatabaseManager:
    """
    Quản lý & Tự động hóa Cơ sở dữ liệu cho Graft Code Agent.
    - Tự động phát hiện nhu cầu CSDL (MySQL, MariaDB, SQLite, PostgreSQL).
    - Quét các file cấu hình kết nối (ketnoi.php, connect.php, config.php, database.php, .env,...).
    - Quét các file dump .sql và nhận diện chính xác bảng mã (UTF-8, UTF-16, Latin-1,...).
    - Tự động kiểm tra trạng thái MySQL Server (Port 3306), kiểm tra database và số lượng bảng.
    - Sinh lệnh / script tự động tạo CSDL và import toàn bộ dữ liệu mà KHÔNG cần người dùng thao tác thủ công.
    """

    @staticmethod
    def is_port_open(host: str = "127.0.0.1", port: int = 3306, timeout: float = 0.5) -> bool:
        """Kiểm tra cổng dịch vụ CSDL có đang mở hay không."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            res = s.connect_ex((host, port))
            s.close()
            return res == 0
        except Exception:
            return False

    @classmethod
    def get_mysql_cli_path(cls) -> Optional[str]:
        """Tự động phát hiện đường dẫn thực thi của mysql CLI trên hệ thống."""
        import shutil
        import glob
        p = shutil.which("mysql")
        if p:
            return p
        patterns = [
            r"C:\laragon\bin\mysql\*\bin\mysql.exe",
            r"C:\xampp\mysql\bin\mysql.exe",
            r"C:\Program Files\MySQL\*\bin\mysql.exe",
            r"C:\Program Files (x86)\MySQL\*\bin\mysql.exe"
        ]
        for pat in patterns:
            matches = glob.glob(pat)
            if matches:
                return matches[0]
        return None

    @classmethod
    def build_init_terminal_command(cls, db_info: Dict[str, Any], project_dir: Optional[Path] = None) -> str:
        """
        Sinh câu lệnh terminal thực thi trực tiếp (CLI) để khởi tạo CSDL và nạp SQL.
        TUYỆT ĐỐI KHÔNG sinh bất kỳ file script khuôn mẫu tạm nào vào dự án!
        """
        cli = cls.get_mysql_cli_path()
        db_user = db_info.get("db_user", "root")
        db_pass = db_info.get("db_pass", "")
        db_name = db_info.get("db_name", "")
        sql_files = db_info.get("sql_files", [])
        pwd_arg = f" -p{db_pass}" if db_pass else ""

        if cli and db_name:
            if sql_files:
                first_sql = sql_files[0].replace("\\", "/")
                is_utf16 = False
                try:
                    p = Path(first_sql)
                    if not p.is_absolute() and project_dir:
                        p = project_dir / p
                    if p.exists():
                        head = p.read_bytes()[:500]
                        if head.startswith((b'\xff\xfe', b'\xfe\xff')) or b'\x00' in head:
                            is_utf16 = True
                except Exception:
                    pass

                if is_utf16:
                    # Tệp SQL UTF-16LE (Unicode) được PowerShell giải mã tự động sang UTF-8 và pipe vào MySQL CLI
                    return f'powershell -NoProfile -ExecutionPolicy Bypass -Command "& \'{cli}\' -u {db_user}{pwd_arg} -e \'CREATE DATABASE IF NOT EXISTS {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\'; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-Content \'{first_sql}\' -Encoding Unicode | & \'{cli}\' -u {db_user}{pwd_arg} --default-character-set=utf8mb4 {db_name}"'
                else:
                    return f'"{cli}" -u {db_user}{pwd_arg} -e "CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; USE `{db_name}`; SOURCE {first_sql};"'
            return f'"{cli}" -u {db_user}{pwd_arg} -e "CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"'

        # Fallback dùng inline php nếu máy có PHP
        if db_name:
            host = db_info.get("db_host", "127.0.0.1")
            return f'php -r "$c = @new mysqli(\'{host}\', \'{db_user}\', \'{db_pass}\'); if ($c->connect_error) {{ exit(1); }} $c->query(\'CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci\');"'

        return ""

    @classmethod
    def find_sql_files(cls, project_dir: Path) -> List[Path]:
        """Tìm tất cả các tệp dump SQL trong dự án (loại trừ các thư mục rác)."""
        ignored_dirs = {".git", "vendor", "node_modules", ".venv", "venv", "storage", "cache", "build", "dist"}
        sql_files = []
        try:
            for root, dirs, files in os.walk(project_dir):
                dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]
                for f in files:
                    if f.lower().endswith(".sql"):
                        sql_files.append(Path(root) / f)
        except Exception:
            pass
        return sql_files

    @classmethod
    def detect_database_requirements(cls, project_dir: Path, actual_pdir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
        """
        Phân tích mã nguồn để phát hiện dự án có sử dụng cơ sở dữ liệu hay không.
        Trả về dictionary chi tiết về database hoặc None nếu dự án không dùng CSDL.
        """
        if actual_pdir is None:
            actual_pdir = project_dir

        sql_files = cls.find_sql_files(project_dir)

        db_name = None
        db_user = "root"
        db_pass = ""
        db_host = "127.0.0.1"
        db_port = 3306
        engine = "mysql"
        found_in_file = None

        # 1. Quét các file PHP cấu hình kết nối phổ biến
        php_conn_files = [
            "ketnoi.php", "connect.php", "config.php", "database.php", "db.php",
            "connection.php", "config/database.php", "include/connect.php",
            "includes/connect.php", "inc/connect.php", "config/connect.php",
            "shop/ketnoi.php", "shop/connect.php"
        ]

        search_paths = [actual_pdir, project_dir]
        checked_files = set()

        for sp in search_paths:
            for rel in php_conn_files:
                fpath = sp / rel
                if fpath.exists() and fpath.is_file() and str(fpath) not in checked_files:
                    checked_files.add(str(fpath))
                    try:
                        content = fpath.read_text(encoding="utf-8-sig", errors="replace")
                        m_dbname = re.search(r'\$(?:db_name|dbname|database|db)\s*=\s*[\'"]([a-zA-Z0-9_-]+)[\'"]', content, re.IGNORECASE)
                        if m_dbname:
                            db_name = m_dbname.group(1).strip()
                            found_in_file = fpath.relative_to(project_dir).as_posix()
                        
                        m_user = re.search(r'\$(?:db_user|dbuser|username|user)\s*=\s*[\'"]([a-zA-Z0-9_-]*)[\'"]', content, re.IGNORECASE)
                        if m_user and m_user.group(1):
                            db_user = m_user.group(1).strip()

                        m_pass = re.search(r'\$(?:db_pass|dbpass|password|pass)\s*=\s*[\'"]([^\'"]*)[\'"]', content, re.IGNORECASE)
                        if m_pass:
                            db_pass = m_pass.group(1).strip()

                        m_host = re.search(r'\$(?:db_host|dbhost|host)\s*=\s*[\'"]([a-zA-Z0-9_.-]+)[\'"]', content, re.IGNORECASE)
                        if m_host:
                            val = m_host.group(1).strip()
                            db_host = "127.0.0.1" if val.lower() == "localhost" else val

                        if not db_name:
                            m_sel = re.search(r'mysqli_select_db\s*\(\s*\$[a-zA-Z0-9_]+\s*,\s*[\'"]([a-zA-Z0-9_-]+)[\'"]', content)
                            if m_sel:
                                db_name = m_sel.group(1).strip()
                                found_in_file = fpath.relative_to(project_dir).as_posix()

                        if not db_name:
                            m_conn4 = re.search(r'mysqli_connect\s*\([^,]+,[^,]+,[^,]+,\s*[\'"]([a-zA-Z0-9_-]+)[\'"]', content)
                            if m_conn4:
                                db_name = m_conn4.group(1).strip()
                                found_in_file = fpath.relative_to(project_dir).as_posix()

                        if db_name:
                            break
                    except Exception:
                        pass
            if db_name:
                break

        # 2. Kiểm tra .env hoặc .env.example
        if not db_name:
            for env_name in [".env", ".env.example"]:
                for sp in search_paths:
                    env_path = sp / env_name
                    if env_path.exists() and env_path.is_file():
                        try:
                            env_txt = env_path.read_text(encoding="utf-8-sig", errors="replace")
                            m_db = re.search(r'DB_DATABASE=([a-zA-Z0-9_-]+)', env_txt)
                            if m_db and m_db.group(1) and m_db.group(1) != "forge":
                                db_name = m_db.group(1).strip()
                                found_in_file = env_path.relative_to(project_dir).as_posix()
                            m_u = re.search(r'DB_USERNAME=([a-zA-Z0-9_-]+)', env_txt)
                            if m_u:
                                db_user = m_u.group(1).strip()
                            m_p = re.search(r'DB_PASSWORD=([^\r\n]*)', env_txt)
                            if m_p:
                                db_pass = m_p.group(1).strip()
                            if db_name:
                                break
                        except Exception:
                            pass
                if db_name:
                    break

        # 3. Nếu chưa tìm thấy trong config nhưng có tệp .sql
        if not db_name and sql_files:
            for sf in sql_files:
                try:
                    raw = sf.read_bytes()[:4000]
                    text = ""
                    if raw.startswith(b'\xff\xfe'):
                        text = raw.decode('utf-16', errors='replace')
                    else:
                        text = raw.decode('utf-8', errors='replace')

                    m_create = re.search(r'CREATE\s+DATABASE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?([a-zA-Z0-9_-]+)`?', text, re.IGNORECASE)
                    if m_create:
                        db_name = m_create.group(1).strip()
                        found_in_file = sf.relative_to(project_dir).as_posix()
                        break

                    m_use = re.search(r'USE\s+`?([a-zA-Z0-9_-]+)`?', text, re.IGNORECASE)
                    if m_use:
                        db_name = m_use.group(1).strip()
                        found_in_file = sf.relative_to(project_dir).as_posix()
                        break
                except Exception:
                    pass

            if not db_name:
                best_sql = sql_files[0]
                db_name = best_sql.stem
                found_in_file = best_sql.relative_to(project_dir).as_posix()

        if not db_name and not sql_files:
            return None

        sql_rel_paths = [f.relative_to(project_dir).as_posix() for f in sql_files]

        return {
            "engine": engine,
            "db_name": db_name,
            "db_user": db_user,
            "db_pass": db_pass,
            "db_host": db_host,
            "db_port": db_port,
            "sql_files": sql_rel_paths,
            "config_file": found_in_file,
            "has_sql_files": len(sql_rel_paths) > 0
        }

    @classmethod
    def check_database_status(cls, db_info: Dict[str, Any]) -> Dict[str, Any]:
        host = db_info.get("db_host", "127.0.0.1")
        port = db_info.get("db_port", 3306)
        user = db_info.get("db_user", "root")
        password = db_info.get("db_pass", "")
        dbname = db_info.get("db_name", "")

        is_running = cls.is_port_open(host, port)
        if not is_running:
            return {
                "server_active": False,
                "db_exists": False,
                "table_count": 0,
                "needs_init": True,
                "error": f"Không thể kết nối tới MySQL Server tại {host}:{port}. Cổng 3306 chưa mở."
            }

        php_check_code = f"""
        $c = @new mysqli('{host}', '{user}', '{password}', '', {port});
        if ($c->connect_error) {{
            echo json_encode(['connected' => false, 'error' => $c->connect_error]);
            exit;
        }}
        $r = $c->query("SHOW DATABASES LIKE '{dbname}'");
        $exists = ($r && $r->num_rows > 0);
        $tbl_cnt = 0;
        if ($exists) {{
            $c->select_db('{dbname}');
            $tr = $c->query('SHOW TABLES');
            $tbl_cnt = $tr ? $tr->num_rows : 0;
        }}
        echo json_encode(['connected' => true, 'exists' => $exists, 'tables' => $tbl_cnt]);
        """

        try:
            p = subprocess.run(["php", "-r", php_check_code], capture_output=True, text=True, timeout=3.0)
            out = p.stdout.strip()
            if out and out.startswith("{"):
                import json
                data = json.loads(out)
                if data.get("connected"):
                    db_exists = data.get("exists", False)
                    tbl_count = data.get("tables", 0)
                    needs_init = (not db_exists) or (tbl_count == 0 and db_info.get("has_sql_files", False))
                    return {
                        "server_active": True,
                        "db_exists": db_exists,
                        "table_count": tbl_count,
                        "needs_init": needs_init,
                        "error": None
                    }
        except Exception:
            pass

        return {
            "server_active": is_running,
            "db_exists": False,
            "table_count": 0,
            "needs_init": True,
            "error": None
        }
