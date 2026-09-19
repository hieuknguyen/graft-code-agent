import os
import sys
import json
import shutil
import platform
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from .database_manager import DatabaseManager

class EnvironmentInspector:
    """
    Chẩn đoán môi trường máy tính (Host Environment) và tình trạng dự án (Project Setup).
    Phát hiện ngôn ngữ/runtime đã cài trên máy, phát hiện thiếu thư viện (vendor, node_modules, .env,...),
    và đề xuất lộ trình khởi chạy dự án chính xác.
    """

    SUPPORTED_RUNTIMES = [
        {"cmd": "php", "name": "PHP", "ver_flag": "-v", "install": "Tải tại https://windows.php.net hoặc chạy `winget install PHP.PHP.8.3`"},
        {"cmd": "composer", "name": "Composer", "ver_flag": "--version", "install": "Tải tại https://getcomposer.org hoặc chạy `winget install Composer.Composer`"},
        {"cmd": "node", "name": "Node.js", "ver_flag": "-v", "install": "Tải tại https://nodejs.org hoặc chạy `winget install OpenJS.NodeJS`"},
        {"cmd": "npm", "name": "npm", "ver_flag": "-v", "install": "Tự động đi kèm với Node.js"},
        {"cmd": "yarn", "name": "Yarn", "ver_flag": "-v", "install": "Cài qua `npm install -g yarn`"},
        {"cmd": "pnpm", "name": "pnpm", "ver_flag": "-v", "install": "Cài qua `npm install -g pnpm`"},
        {"cmd": "python", "name": "Python", "ver_flag": "--version", "install": "Tải tại https://python.org hoặc qua Microsoft Store"},
        {"cmd": "pip", "name": "pip", "ver_flag": "--version", "install": "Tự động đi kèm với Python"},
        {"cmd": "git", "name": "Git", "ver_flag": "--version", "install": "Tải tại https://git-scm.com hoặc `winget install Git.Git`"},
        {"cmd": "docker", "name": "Docker", "ver_flag": "-v", "install": "Tải Docker Desktop tại https://docker.com"},
        {"cmd": "go", "name": "Go", "ver_flag": "version", "install": "Tải tại https://go.dev"},
        {"cmd": "rustc", "name": "Rust", "ver_flag": "--version", "install": "Cài đặt tại https://rustup.rs"}
    ]

    _cached_runtimes: Optional[Dict[str, Any]] = None

    @classmethod
    def check_system_runtimes(cls, force_refresh: bool = False) -> Dict[str, Any]:
        """Quét và kiểm tra các runtime / CLI tool đã được cài trên máy tính."""
        if cls._cached_runtimes and not force_refresh:
            return cls._cached_runtimes

        results = {}
        for r in cls.SUPPORTED_RUNTIMES:
            cmd = r["cmd"]
            path = shutil.which(cmd)
            installed = path is not None
            version = None
            if installed:
                try:
                    p = subprocess.run(
                        [cmd, r["ver_flag"]],
                        capture_output=True,
                        text=True,
                        timeout=2.0,
                        shell=(os.name == 'nt')
                    )
                    out = (p.stdout or p.stderr or "").strip()
                    if out:
                        version = out.splitlines()[0].strip()
                except Exception as e:
                    version = f"Lỗi lấy version: {e}"

            results[cmd] = {
                "name": r["name"],
                "installed": installed,
                "path": path,
                "version": version,
                "install_hint": r["install"]
            }

        # Kiểm tra dịch vụ Cơ sở dữ liệu MySQL / MariaDB
        mysql_path = shutil.which("mysql")
        if not mysql_path:
            for cand in [
                Path("C:/laragon/bin/mysql"),
                Path("D:/laragon/bin/mysql"),
                Path("C:/xampp/mysql/bin"),
                Path("D:/xampp/mysql/bin"),
                Path("C:/Program Files/MySQL"),
                Path("C:/Program Files/MariaDB")
            ]:
                if cand.exists():
                    for exe in cand.rglob("mysql.exe"):
                        mysql_path = str(exe)
                        break
                if mysql_path:
                    break

        import socket
        port_3306_active = False
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            res = s.connect_ex(("127.0.0.1", 3306))
            port_3306_active = (res == 0)
            s.close()
        except Exception:
            pass

        mysql_installed = (mysql_path is not None) or port_3306_active
        mysql_ver = "Đang chạy trên cổng 3306" if port_3306_active else ("Đã cài đặt tại " + str(Path(mysql_path).parent.name) if mysql_path else None)

        results["mysql"] = {
            "name": "MySQL / MariaDB",
            "installed": mysql_installed,
            "path": mysql_path,
            "port_3306_active": port_3306_active,
            "version": mysql_ver,
            "install_hint": "Bật dịch vụ MySQL qua Laragon / XAMPP hoặc cài đặt MySQL Server"
        }

        cls._cached_runtimes = results
        return results

    @classmethod
    def _resolve_actual_root_and_web_root(cls, pdir: Path) -> Tuple[Path, str, str]:
        """
        Xác định thư mục mã nguồn thực tế và thư mục document root (nếu dự án bị lồng).
        Trả về: (actual_pdir, rel_root, web_root_rel)
        - actual_pdir: Path tuyệt đối của thư mục chứa mã nguồn chính (chứa composer.json, package.json,...)
        - rel_root: đường dẫn tương đối từ pdir tới actual_pdir (ví dụ 'webquanlynhahang')
        - web_root_rel: đường dẫn tương đối từ pdir tới thư mục chứa index.php/index.html (ví dụ 'webquanlynhahang/shop')
        """
        has_direct_marker = (
            (pdir / "artisan").exists() or
            (pdir / "composer.json").exists() or
            (pdir / "package.json").exists() or
            (pdir / "requirements.txt").exists() or
            (pdir / "pyproject.toml").exists() or
            (pdir / "manage.py").exists() or
            (pdir / "main.py").exists() or
            (pdir / "go.mod").exists() or
            (pdir / "Cargo.toml").exists() or
            any(pdir.glob("*.php")) or
            any(pdir.glob("*.py"))
        )

        actual_pdir = pdir
        rel_root = ""

        if not has_direct_marker:
            ignored = {".git", "__pycache__", "node_modules", "vendor", ".venv", "venv", "dist", "build"}
            candidate_dirs = [c for c in pdir.iterdir() if c.is_dir() and c.name not in ignored and not c.name.startswith(".")]

            for cdir in candidate_dirs:
                if (
                    (cdir / "artisan").exists() or
                    (cdir / "composer.json").exists() or
                    (cdir / "package.json").exists() or
                    (cdir / "requirements.txt").exists() or
                    (cdir / "pyproject.toml").exists() or
                    (cdir / "manage.py").exists() or
                    (cdir / "main.py").exists() or
                    (cdir / "go.mod").exists() or
                    (cdir / "Cargo.toml").exists() or
                    any(cdir.glob("*.php")) or
                    any(cdir.glob("*.py"))
                ):
                    actual_pdir = cdir
                    rel_root = cdir.relative_to(pdir).as_posix()
                    break

            if actual_pdir == pdir and len(candidate_dirs) == 1:
                actual_pdir = candidate_dirs[0]
                rel_root = candidate_dirs[0].relative_to(pdir).as_posix()

        priority_subdirs = ["public", "shop", "web", "frontend", "src", ""]
        found_web_dir = None
        for sub in priority_subdirs:
            target_check = (actual_pdir / sub / "index.php") if sub else (actual_pdir / "index.php")
            if target_check.exists():
                found_web_dir = target_check.parent
                break
        if not found_web_dir:
            for sub in priority_subdirs:
                target_check = (actual_pdir / sub / "index.html") if sub else (actual_pdir / "index.html")
                if target_check.exists():
                    found_web_dir = target_check.parent
                    break

        if not found_web_dir:
            for f in actual_pdir.rglob("index.php"):
                parts = f.relative_to(actual_pdir).parts
                if not any(p in ("vendor", "node_modules", ".git", "storage") for p in parts):
                    found_web_dir = f.parent
                    break

        web_root_rel = ""
        if found_web_dir:
            web_root_rel = found_web_dir.relative_to(pdir).as_posix()
        elif rel_root:
            web_root_rel = rel_root

        return actual_pdir, rel_root, web_root_rel

    @classmethod
    def inspect_project(cls, project_dir: str) -> Dict[str, Any]:
        """
        Phân tích cấu trúc thư mục dự án để xác định:
        - Loại dự án (Laravel, Node, Python, Go, PHP thuần, v.v.)
        - Hỗ trợ phát hiện thư mục bị lồng (Nested Projects)
        - Tự động định vị Document Root (thư mục chứa index.php / web entrypoint)
        - Các file cấu hình / dependencies (composer.json, package.json, requirements.txt, v.v.)
        - Trạng thái cài đặt: vendor/, node_modules/, .env, v.v.
        - Phân tích thiếu sót (Missing dependencies / runtimes)
        - Đề xuất các bước thực thi (Action Plan)
        """
        pdir = Path(project_dir).resolve()
        if not pdir.exists() or not pdir.is_dir():
            return {"error": f"Thư mục không tồn tại: {project_dir}"}

        runtimes = cls.check_system_runtimes()
        actual_pdir, rel_root, web_root_rel = cls._resolve_actual_root_and_web_root(pdir)

        # 1. Nhận diện loại dự án trên actual_pdir (hoặc pdir)
        project_types = []
        is_laravel = ((actual_pdir / "artisan").exists() and (actual_pdir / "composer.json").exists()) or ((pdir / "artisan").exists() and (pdir / "composer.json").exists())
        is_symfony = ((actual_pdir / "bin" / "console").exists() and (actual_pdir / "composer.json").exists()) or ((pdir / "bin" / "console").exists() and (pdir / "composer.json").exists())
        is_php = (
            (actual_pdir / "composer.json").exists() or
            (pdir / "composer.json").exists() or
            any(actual_pdir.glob("*.php")) or
            any(pdir.glob("*.php")) or
            bool(web_root_rel and (pdir / web_root_rel / "index.php").exists())
        )

        has_package_json = (actual_pdir / "package.json").exists() or (pdir / "package.json").exists()
        is_python = (
            (actual_pdir / "requirements.txt").exists() or (pdir / "requirements.txt").exists() or
            (actual_pdir / "pyproject.toml").exists() or (pdir / "pyproject.toml").exists() or
            (actual_pdir / "manage.py").exists() or (pdir / "manage.py").exists() or
            (actual_pdir / "main.py").exists() or (pdir / "main.py").exists()
        )
        is_go = (actual_pdir / "go.mod").exists() or (pdir / "go.mod").exists()
        is_rust = (actual_pdir / "Cargo.toml").exists() or (pdir / "Cargo.toml").exists()

        framework_name = "Unknown"
        if is_laravel:
            framework_name = "Laravel Framework (PHP)"
            project_types.append("laravel")
        elif is_symfony:
            framework_name = "Symfony (PHP)"
            project_types.append("symfony")
        elif is_php:
            if (actual_pdir / "composer.json").exists():
                framework_name = "PHP Project (Composer / Custom)"
            else:
                framework_name = "PHP Project"
            project_types.append("php")

        if has_package_json:
            framework_name = f"{framework_name} + Node.js" if framework_name != "Unknown" else "Node.js Project"
            project_types.append("node")

        if is_python:
            if (actual_pdir / "manage.py").exists() or (pdir / "manage.py").exists():
                framework_name = "Django (Python)"
            else:
                framework_name = "Python Project"
            project_types.append("python")

        if is_go:
            framework_name = "Go Project"
            project_types.append("go")
        if is_rust:
            framework_name = "Rust Project"
            project_types.append("rust")

        # 2. Kiểm tra chi tiết từng thành phần
        components = {}
        missing_runtimes = []
        missing_dependencies = []
        missing_configs = []
        action_plan = []

        # Tiền tố chuyển thư mục nếu mã nguồn bị lồng trong thư mục con
        cd_prefix = f"cd {rel_root} && " if rel_root else ""

        # --- Kiểm tra PHP / Laravel ---
        if is_laravel or is_php:
            php_installed = runtimes.get("php", {}).get("installed", False)
            composer_installed = runtimes.get("composer", {}).get("installed", False)

            if not php_installed:
                missing_runtimes.append({
                    "name": "PHP",
                    "reason": "Dự án yêu cầu PHP nhưng máy tính chưa cài đặt PHP.",
                    "install_hint": runtimes.get("php", {}).get("install_hint", "")
                })
            if not composer_installed and ((actual_pdir / "composer.json").exists() or (pdir / "composer.json").exists()):
                missing_runtimes.append({
                    "name": "Composer",
                    "reason": "Dự án sử dụng composer.json nhưng máy tính chưa có Composer.",
                    "install_hint": runtimes.get("composer", {}).get("install_hint", "")
                })

            composer_json = (actual_pdir / "composer.json") if (actual_pdir / "composer.json").exists() else (pdir / "composer.json")
            vendor_dir = (actual_pdir / "vendor") if (actual_pdir / "vendor").exists() else (pdir / "vendor")
            has_vendor = vendor_dir.exists() and vendor_dir.is_dir() and any(vendor_dir.iterdir())
            components["composer"] = {
                "has_composer_json": composer_json.exists(),
                "has_vendor": has_vendor
            }

            if composer_json.exists() and not has_vendor:
                missing_dependencies.append({
                    "name": "vendor (PHP Dependencies)",
                    "reason": "Thư mục `vendor/` chưa tồn tại. Dự án mới clone về cần cài thư viện.",
                    "cmd": f"{cd_prefix}composer install",
                    "desc": "Cài đặt các gói PHP qua Composer"
                })

            # Kiểm tra .env cho Laravel
            if is_laravel:
                env_file = (actual_pdir / ".env") if (actual_pdir / ".env").exists() else (pdir / ".env")
                env_example = (actual_pdir / ".env.example") if (actual_pdir / ".env.example").exists() else (pdir / ".env.example")
                has_env = env_file.exists()
                has_env_example = env_example.exists()

                components["env"] = {
                    "has_env": has_env,
                    "has_env_example": has_env_example
                }

                if not has_env and has_env_example:
                    copy_cmd = f"{cd_prefix}copy .env.example .env" if os.name == 'nt' else f"{cd_prefix}cp .env.example .env"
                    missing_configs.append({
                        "name": ".env (Môi Trường Cấu Hình)",
                        "reason": "File `.env` chưa tồn tại. Cần tạo từ `.env.example`.",
                        "cmd": copy_cmd,
                        "desc": "Sao chép cấu hình mẫu sang .env"
                    })

                if has_env:
                    try:
                        env_content = env_file.read_text(encoding="utf-8", errors="replace")
                        if "APP_KEY=" in env_content and not any(line.startswith("APP_KEY=base64:") for line in env_content.splitlines()):
                            missing_configs.append({
                                "name": "APP_KEY (Khóa Mã Hóa Laravel)",
                                "reason": "Chưa sinh mã khóa APP_KEY trong file .env.",
                                "cmd": f"{cd_prefix}php artisan key:generate",
                                "desc": "Tạo mã khóa bảo mật ứng dụng Laravel"
                            })
                    except Exception:
                        pass

        # --- Kiểm tra Node.js ---
        if has_package_json:
            node_installed = runtimes.get("node", {}).get("installed", False)
            npm_installed = runtimes.get("npm", {}).get("installed", False)

            if not node_installed:
                missing_runtimes.append({
                    "name": "Node.js",
                    "reason": "Dự án có package.json nhưng máy tính chưa cài đặt Node.js.",
                    "install_hint": runtimes.get("node", {}).get("install_hint", "")
                })

            node_modules = (actual_pdir / "node_modules") if (actual_pdir / "node_modules").exists() else (pdir / "node_modules")
            has_node_modules = node_modules.exists() and node_modules.is_dir() and any(node_modules.iterdir())
            components["npm"] = {
                "has_package_json": True,
                "has_node_modules": has_node_modules
            }

            if not has_node_modules:
                missing_dependencies.append({
                    "name": "node_modules (JavaScript / Frontend Dependencies)",
                    "reason": "Thư mục `node_modules/` chưa có.",
                    "cmd": f"{cd_prefix}npm install",
                    "desc": "Cài đặt thư viện frontend / Node.js"
                })

        # --- Kiểm tra Python ---
        if is_python:
            py_installed = runtimes.get("python", {}).get("installed", False)
            if not py_installed:
                missing_runtimes.append({
                    "name": "Python",
                    "reason": "Dự án Python nhưng máy tính chưa cài đặt Python.",
                    "install_hint": runtimes.get("python", {}).get("install_hint", "")
                })

            req_file = (actual_pdir / "requirements.txt") if (actual_pdir / "requirements.txt").exists() else (pdir / "requirements.txt")
            venv_dir = (actual_pdir / ".venv") if (actual_pdir / ".venv").exists() else (pdir / ".venv")
            if not venv_dir.exists():
                venv_dir = (actual_pdir / "venv") if (actual_pdir / "venv").exists() else (pdir / "venv")
            has_venv = venv_dir.exists() and venv_dir.is_dir()
            components["python"] = {
                "has_requirements": req_file.exists(),
                "has_venv": has_venv
            }

            if req_file.exists() and not has_venv:
                missing_dependencies.append({
                    "name": "Python Virtualenv & Packages",
                    "reason": "Chưa tạo môi trường ảo hoặc cài đặt thư viện từ requirements.txt.",
                    "cmd": f"{cd_prefix}python -m venv .venv && .\\.venv\\Scripts\\pip install -r requirements.txt" if os.name == 'nt' else f"{cd_prefix}python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt",
                    "desc": "Tạo virtualenv và cài đặt dependencies"
                })


        # --- Kiểm tra Cơ sở dữ liệu (Database) ---
        db_info = DatabaseManager.detect_database_requirements(pdir, actual_pdir)
        if db_info:
            db_status = DatabaseManager.check_database_status(db_info)
            components["database"] = {
                "info": db_info,
                "status": db_status
            }
            if not db_status.get("server_active", False):
                missing_runtimes.append({
                    "name": "Dịch vụ MySQL (Cổng 3306)",
                    "reason": f"Dự án yêu cầu CSDL MySQL `{db_info['db_name']}` nhưng máy chủ MySQL (Laragon / XAMPP) chưa được khởi động.",
                    "install_hint": "Bật dịch vụ MySQL qua Laragon / XAMPP hoặc chạy `net start mysql`"
                })
            elif db_status.get("needs_init", False):
                sql_list = ", ".join(db_info.get("sql_files", []))
                init_cmd = DatabaseManager.build_init_terminal_command(db_info, project_dir=pdir)
                missing_dependencies.append({
                    "name": f"CSDL MySQL `{db_info['db_name']}`",
                    "reason": f"Dự án cần CSDL `{db_info['db_name']}` ({sql_list}) nhưng database chưa tồn tại hoặc chưa có bảng dữ liệu.",
                    "cmd": init_cmd if init_cmd else f"# Cần tạo CSDL `{db_info['db_name']}`",
                    "desc": f"Tạo CSDL `{db_info['db_name']}` và nạp dữ liệu từ {sql_list}"
                })

        # 3. Lập Action Plan tổng thể
        if missing_runtimes:
            for mr in missing_runtimes:
                action_plan.append({
                    "type": "INSTALL_RUNTIME",
                    "name": mr["name"],
                    "desc": mr["reason"],
                    "install_hint": mr["install_hint"]
                })

        for mc in missing_configs:
            action_plan.append({
                "type": "CONFIG",
                "name": mc["name"],
                "cmd": mc["cmd"],
                "desc": mc["desc"]
            })

        for md in missing_dependencies:
            action_plan.append({
                "type": "DEPENDENCY",
                "name": md["name"],
                "cmd": md["cmd"],
                "desc": md["desc"]
            })

        # Lệnh chạy server cuối cùng
        if is_laravel:
            action_plan.append({
                "type": "START_SERVER",
                "name": "Khởi động Web Server Laravel",
                "cmd": f"{cd_prefix}php artisan serve",
                "desc": "Khởi chạy máy chủ HTTP nội bộ Laravel trên cổng 8000"
            })
        elif is_php:
            cmd = f"php -S 127.0.0.1:8000 -t {web_root_rel}" if web_root_rel and web_root_rel != "." else "php -S 127.0.0.1:8000"
            action_plan.append({
                "type": "START_SERVER",
                "name": "Khởi động PHP Web Server",
                "cmd": cmd,
                "desc": f"Khởi chạy máy chủ PHP Built-in Server tại cổng 8000 (Document root: {web_root_rel or 'root'})"
            })
        elif has_package_json and not is_laravel:
            action_plan.append({
                "type": "START_SERVER",
                "name": "Khởi động Frontend / Node Dev Server",
                "cmd": f"{cd_prefix}npm run dev",
                "desc": "Chạy máy chủ phát triển Vite / Next.js / Node"
            })
        elif is_python:
            entry = "run.py" if (actual_pdir / "run.py").exists() else ("main.py" if (actual_pdir / "main.py").exists() else "manage.py runserver")
            action_plan.append({
                "type": "START_SERVER",
                "name": "Khởi động Ứng dụng Python",
                "cmd": f"{cd_prefix}python {entry}",
                "desc": "Khởi chạy ứng dụng Python"
            })

        ready_to_run = (len(missing_runtimes) == 0 and len(missing_dependencies) == 0 and len(missing_configs) == 0)

        return {
            "project_dir": str(pdir),
            "actual_dir": str(actual_pdir),
            "rel_root": rel_root,
            "web_root_rel": web_root_rel,
            "project_name": pdir.name,
            "framework": framework_name,
            "project_types": project_types,
            "ready_to_run": ready_to_run,
            "missing_runtimes": missing_runtimes,
            "missing_dependencies": missing_dependencies,
            "missing_configs": missing_configs,
            "action_plan": action_plan,
            "components": components,
            "runtimes": runtimes
        }

    @classmethod
    def format_markdown_report(cls, inspection: Dict[str, Any]) -> str:
        """Tạo báo cáo Markdown trực quan để gửi vào chat hoặc inject vào context prompt."""
        if "error" in inspection:
            return f"❌ **Lỗi chẩn đoán**: {inspection['error']}"

        pname = inspection.get("project_name", "Dự án")
        framework = inspection.get("framework", "Không rõ")
        runtimes = inspection.get("runtimes", {})
        missing_runtimes = inspection.get("missing_runtimes", [])
        missing_deps = inspection.get("missing_dependencies", [])
        missing_configs = inspection.get("missing_configs", [])
        ready = inspection.get("ready_to_run", False)
        rel_root = inspection.get("rel_root", "")
        web_root = inspection.get("web_root_rel", "")

        lines = [
            f"### 🔍 BÁO CÁO CHẨN ĐOÁN DỰ ÁN & HỆ THỐNG ({pname.upper()})",
            f"• **Công nghệ / Framework:** `{framework}`",
            f"• **Thư mục:** `{inspection.get('project_dir')}`",
        ]
        if rel_root:
            lines.append(f"• **Cấu trúc lồng:** `{rel_root}/` (Mã nguồn chính nằm trong thư mục con)")
        if web_root:
            lines.append(f"• **Web Document Root:** `{web_root}/` (Chứa tệp index.php / web entrypoint)")

        lines.append("")
        lines.append("#### 1. Tình Trạng Runtime Trên Máy Tính (Host Runtimes):")

        for cmd, info in runtimes.items():
            if cmd in ("php", "composer", "node", "npm", "python", "git", "mysql"):
                status_icon = "✅" if info["installed"] else "❌"
                ver_text = f"(`{info['version']}`)" if info['installed'] and info['version'] else ("(Chưa cài đặt)" if not info['installed'] else "")
                lines.append(f"- {status_icon} **{info['name']}**: {ver_text}")

        lines.append("")
        lines.append("#### 2. Tình Trạng Cấu Hình & Thư Viện Dự Án:")
        comps = inspection.get("components", {})
        if "composer" in comps:
            c = comps["composer"]
            v_icon = "✅ Có sẵn" if c["has_vendor"] else "⚠️ Chưa cài (Thiếu vendor/)"
            lines.append(f"- **PHP Composer**: composer.json có sẵn | `vendor/`: {v_icon}")

        if "npm" in comps:
            n = comps["npm"]
            nm_icon = "✅ Có sẵn" if n["has_node_modules"] else "⚠️ Chưa cài (Thiếu node_modules/)"
            lines.append(f"- **Node.js**: package.json có sẵn | `node_modules/`: {nm_icon}")

        if "env" in comps:
            e = comps["env"]
            env_icon = "✅ Đã có" if e["has_env"] else ("⚠️ Chưa có (Có .env.example mẫu)" if e["has_env_example"] else "❌ Không có")
            lines.append(f"- **Môi trường .env**: {env_icon}")

        if "python" in comps:
            p = comps["python"]
            venv_icon = "✅ Có sẵn" if p["has_venv"] else "⚠️ Chưa có virtualenv"
            lines.append(f"- **Python Env**: requirements.txt | virtualenv: {venv_icon}")

        if "database" in comps:
            d = comps["database"]
            d_info = d.get("info", {})
            d_stat = d.get("status", {})
            d_name = d_info.get("db_name", "Unknown")
            d_tbls = d_stat.get("table_count", 0)
            d_active = d_stat.get("server_active", False)
            if not d_active:
                d_icon = "❌ MySQL chưa bật (Cổng 3306 đóng)"
            elif d_stat.get("needs_init", False):
                d_icon = f"⚠️ Cần khởi tạo & nạp dữ liệu ({len(d_info.get('sql_files', []))} tệp SQL)"
            else:
                d_icon = f"✅ Sẵn sàng ({d_tbls} bảng)"
            lines.append(f"- **Cơ sở dữ liệu (MySQL)**: `{d_name}` | Trạng thái: {d_icon}")

        lines.append("")
        if missing_runtimes:
            lines.append("#### ⚠️ CẢNH BÁO: MÁY TÍNH THIẾU CÔNG CỤ CẦN THIẾT:")
            for mr in missing_runtimes:
                lines.append(f"- ❌ **{mr['name']}**: {mr['reason']}")
                lines.append(f"  👉 *Cách cài:* {mr['install_hint']}")
            lines.append("")

        if missing_configs or missing_deps:
            lines.append("#### 📋 CÁC BƯỚC CẦN CHUẨN BỊ (DỰ ÁN MỚI CLONE):")
            step = 1
            for mc in missing_configs:
                lines.append(f"{step}. **{mc['name']}**: `{mc['cmd']}` ({mc['desc']})")
                step += 1
            for md in missing_deps:
                lines.append(f"{step}. **{md['name']}**: `{md['cmd']}` ({md['desc']})")
                step += 1
            lines.append("")

        if ready:
            lines.append("🎉 **Dự án đã đầy đủ mọi điều kiện để khởi chạy ngay!**")
            plan = inspection.get("action_plan", [])
            server_cmds = [p for p in plan if p.get("type") == "START_SERVER"]
            if server_cmds:
                lines.append(f"👉 **Lệnh khởi chạy kiến nghị:** `{server_cmds[0]['cmd']}` ({server_cmds[0].get('desc', '')})")
        else:
            lines.append("👉 **Khuyến nghị:** Cần thực hiện các bước chuẩn bị trên trước khi khởi chạy server.")

        return "\n".join(lines)
