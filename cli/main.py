import sys
import os
from pathlib import Path
from config import load_config, save_config
from core.agent import GraftAgent
from .ui import console, print_banner, print_token_stats, render_diff

import argparse

def run_cli():
    parser = argparse.ArgumentParser(description="Graft Code Agent - AI Surgical Coding Assistant")
    parser.add_argument("--task", type=str, help="Yêu cầu lập trình chạy 1 lần (One-shot mode)")
    parser.add_argument("--file", type=str, help="Tệp mã nguồn mục tiêu cần thao tác")
    parser.add_argument("--auto", action="store_true", help="Tự động áp dụng cấy ghép không cần hỏi y/n")
    parser.add_argument("--dir", type=str, default=None, help="Thư mục gốc của dự án (mặc định: thư mục hiện tại)")
    parser.add_argument("--ui", action="store_true", help="Khởi chạy giao diện Web UI Dashboard trên trình duyệt")
    parser.add_argument("--port", type=int, default=7890, help="Cổng chạy Web UI Dashboard (mặc định: 7890)")
    parser.add_argument("--desktop", action="store_true", help="Khởi chạy giao diện Native Desktop App (PySide6)")
    parser.add_argument("--cli", action="store_true", help="Khởi chạy giao diện Terminal dòng lệnh")
    args = parser.parse_args()

    if args.ui:
        from web_ui import run_web
        root_dir = os.path.abspath(args.dir) if args.dir else os.getcwd()
        run_web(root_dir=root_dir, port=args.port)
        return

    if args.desktop or (not args.cli and not args.task):
        try:
            from desktop_app import run_desktop
            root_dir = os.path.abspath(args.dir) if args.dir else os.getcwd()
            sys.exit(run_desktop(root_dir))
        except Exception as e:
            # Fallback to CLI if GUI fails
            pass

    print_banner()
    cfg = load_config()
    if args.auto:
        cfg.auto_apply = True

    root_dir = os.path.abspath(args.dir) if args.dir else os.getcwd()
    console.print(f"[bold blue]Codebase Root:[/] {root_dir}")
    console.print(f"[bold blue]Gateway URL:[/] {cfg.gateway_url} (Model: {cfg.model})")

    agent = GraftAgent(cfg, root_dir)
    with console.status("[bold green]Đang quét AST biểu tượng & cây quan hệ dự án..."):
        agent.scan()
    console.print(f"[green]Đã phân tích xong {len(agent.graph.files)} tệp mã nguồn.[/green]\n")

    # Xử lý One-shot mode nếu có --task
    if args.task:
        console.print(f"[bold magenta]Đang thực thi tác vụ:[/] {args.task}")
        with console.status("[bold magenta]AI đang phân tích và tính toán phẫu thuật ghép code..."):
            res = agent.plan_and_graft(args.task, target_file=args.file)

        if not res.get("success"):
            console.print(f"[bold red]Lỗi:[/] {res.get('error')}")
            return

        print_token_stats(res.get("tokens", {}))
        actions = res.get("actions", [])
        if not actions:
            console.print(Panel(res.get("response", ""), title="Phản hồi từ AI", border_style="cyan"))
            return

        for act in actions:
            if not act["success"]:
                console.print(f"[bold red]Graft thất bại trên {act['file']}:[/] {act.get('error')}")
                continue

            console.print(f"\n[bold green]Cấy ghép thành công:[/] {act['msg']}")
            render_diff(act["diff"])
            apply = cfg.auto_apply
            if not apply:
                confirm = console.input(f"[bold yellow]Áp dụng thay đổi vào `{act['file']}`? (y/n): [/]").strip().lower()
                apply = (confirm == 'y' or confirm == 'yes')

            if apply:
                agent.apply_action(act)
                console.print(f"[bold green]Đã ghi file `{act['file']}` an toàn vào đĩa cứng.[/bold green]")
            else:
                console.print("[dim]Đã bỏ qua thay đổi.[/dim]")
        return

    console.print("[dim]Gõ lệnh hoặc yêu cầu lập trình. Lệnh hỗ trợ: /tree, /scan, /find <name>, /undo, /config, /exit[/dim]\n")

    while True:
        try:
            user_input = console.input("[bold cyan]graft-agent>[/] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Đang thoát Graft Agent. Hẹn gặp lại![/yellow]")
            break

        if not user_input:
            continue

        if user_input == "/exit":
            console.print("[yellow]Tạm biệt![/yellow]")
            break

        if user_input == "/scan":
            with console.status("[bold green]Đang quét lại..."):
                agent.scan()
            console.print(f"[green]✓ Đã quét lại {len(agent.graph.files)} tệp.[/green]")
            continue

        if user_input == "/tree":
            console.print(Panel(agent.graph.get_compact_summary(), title="Codebase AST Map", border_style="blue"))
            continue

        if user_input.startswith("/find "):
            sym_name = user_input[6:].strip()
            locs = agent.graph.find_symbol(sym_name)
            if not locs:
                console.print(f"[red]Không tìm thấy biểu tượng '{sym_name}'[/red]")
            else:
                for l in locs:
                    console.print(f"• [bold green]{l['type']}[/] [cyan]{sym_name}[/] trong `{l['file']}` (dòng {l['line']})")
            continue

        if user_input == "/undo":
            succ, msg = agent.undo()
            console.print(f"[{'green' if succ else 'red'}]{msg}[/]")
            continue

        # Xử lý yêu cầu lập trình & cấy ghép code
        with console.status("[bold magenta]AI đang phân tích và tính toán phẫu thuật ghép code..."):
            res = agent.plan_and_graft(user_input)

        if not res.get("success"):
            console.print(f"[bold red]Lỗi:[/] {res.get('error')}")
            continue

        print_token_stats(res.get("tokens", {}))

        actions = res.get("actions", [])
        if not actions:
            console.print(Panel(res.get("response", ""), title="Phản hồi từ AI (Không có thao tác Graft)", border_style="cyan"))
            continue

        for act in actions:
            if not act["success"]:
                console.print(f"[bold red]Graft thất bại trên {act['file']}:[/] {act.get('error')}")
                continue

            console.print(f"\n[bold green]✓ Cấy ghép thành công:[/] {act['msg']}")
            if act["verified"]:
                console.print(f"[bold green]✓ Kiểm tra cú pháp:[/] {act['verify_msg']}")
            else:
                console.print(f"[bold red]✗ Cảnh báo cú pháp:[/] {act['verify_msg']}")

            render_diff(act["diff"])

            # Xác nhận trước khi áp dụng nếu auto_apply = False
            apply = cfg.auto_apply
            if not apply:
                confirm = console.input(f"[bold yellow]Áp dụng thay đổi vào `{act['file']}`? (y/n): [/]").strip().lower()
                apply = (confirm == 'y' or confirm == 'yes')

            if apply:
                agent.apply_action(act)
                console.print(f"[bold green]✓ Đã ghi file `{act['file']}` an toàn vào đĩa cứng.[/bold green]")
            else:
                console.print("[dim]Đã bỏ qua thay đổi.[/dim]")

if __name__ == "__main__":
    run_cli()
