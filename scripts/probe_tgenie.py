from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from atlas.tgenie_setup import default_atlas_config_dir

if TYPE_CHECKING:
    from playwright.sync_api import Page


TARGETS = [
    ("sidebar_toggle", "側邊欄展開/收合按鈕"),
    ("new_conversation", "New conversation 按鈕"),
    ("prompt_input", "對話輸入框"),
    ("send_button", "送出對話按鈕，也會在生成時變成 stop generating"),
    ("attach_button", "Attach / 上傳檔案按鈕"),
    ("model_selector", "模型選擇器"),
    ("web_search_toggle", "Web search 開關"),
]

TARGET_DESCRIPTIONS = dict(TARGETS)


INTERACTIVE_SELECTOR = """
button,
a,
input,
textarea,
select,
[role='button'],
[role='textbox'],
[role='combobox'],
[role='menuitem'],
[role='option'],
[contenteditable='true'],
[aria-label],
[placeholder],
[title],
[data-testid],
[data-test],
[data-cy]
"""

def text_preview(value: str | None, limit: int = 120) -> str:
    if not value:
        return ""
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def extract_elements(page: "Page") -> list[dict[str, Any]]:
    return page.evaluate(
        """
        (selector) => {
          const nodes = Array.from(document.querySelectorAll(selector));
          const seen = new Set();
          const elements = [];

          function visible(el) {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.visibility !== 'hidden'
              && style.display !== 'none'
              && rect.width > 0
              && rect.height > 0;
          }

          function labelText(el) {
            if (el.labels && el.labels.length) {
              return Array.from(el.labels).map((label) => label.innerText).join(' ');
            }
            return '';
          }

          for (const el of nodes) {
            if (seen.has(el)) continue;
            seen.add(el);
            const rect = el.getBoundingClientRect();
            elements.push({
              tag: el.tagName.toLowerCase(),
              role: el.getAttribute('role') || '',
              type: el.getAttribute('type') || '',
              text: (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim(),
              ariaLabel: el.getAttribute('aria-label') || '',
              placeholder: el.getAttribute('placeholder') || '',
              title: el.getAttribute('title') || '',
              label: labelText(el).replace(/\\s+/g, ' ').trim(),
              id: el.id || '',
              name: el.getAttribute('name') || '',
              testId: el.getAttribute('data-testid') || el.getAttribute('data-test') || el.getAttribute('data-cy') || '',
              href: el.getAttribute('href') || '',
              visible: visible(el),
              disabled: Boolean(el.disabled) || el.getAttribute('aria-disabled') === 'true',
              bbox: {
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                width: Math.round(rect.width),
                height: Math.round(rect.height),
              },
            });
          }

          return elements
            .filter((element) => element.visible)
            .sort((a, b) => (a.bbox.y - b.bbox.y) || (a.bbox.x - b.bbox.x));
        }
        """,
        INTERACTIVE_SELECTOR,
    )


def element_label(element: dict[str, Any]) -> str:
    bits = [
        element.get("text"),
        element.get("ariaLabel"),
        element.get("placeholder"),
        element.get("label"),
        element.get("title"),
        element.get("testId"),
    ]
    label = " | ".join(text_preview(bit, 60) for bit in bits if bit)
    return label or "(no visible label)"


def print_elements(elements: list[dict[str, Any]]) -> None:
    print("\n目前頁面可見互動元素：")
    for index, element in enumerate(elements):
        bbox = element["bbox"]
        print(
            f"[{index:02d}] "
            f"{element['tag']}"
            f"{'#' + element['id'] if element.get('id') else ''} "
            f"role={element.get('role') or '-'} "
            f"type={element.get('type') or '-'} "
            f"box={bbox['x']},{bbox['y']},{bbox['width']}x{bbox['height']} "
            f"label={element_label(element)}"
        )


def selector_hint(element: dict[str, Any]) -> dict[str, str]:
    if element.get("testId"):
        return {"method": "css", "value": f"[data-testid='{element['testId']}']"}
    if element.get("ariaLabel"):
        return {"method": "get_by_label", "value": element["ariaLabel"]}
    if element.get("placeholder"):
        return {"method": "get_by_placeholder", "value": element["placeholder"]}
    if element.get("role") and element.get("text"):
        return {"method": "get_by_role", "role": element["role"], "name": text_preview(element["text"], 80)}
    if element.get("tag") == "button" and element.get("text"):
        return {"method": "get_by_role", "role": "button", "name": text_preview(element["text"], 80)}
    if element.get("id"):
        return {"method": "css", "value": f"#{element['id']}"}
    return {"method": "manual_review", "value": element_label(element)}


def record_choice(choices: dict[str, Any], target: str, index: int, element: dict[str, Any]) -> None:
    choices[target] = {
        "index": index,
        "description": TARGET_DESCRIPTIONS[target],
        "element": element,
        "selector_hint": selector_hint(element),
    }
    print(f"已記錄 {target}：{element_label(element)}")


def click_element(page: "Page", element: dict[str, Any]) -> None:
    bbox = element["bbox"]
    page.mouse.click(bbox["x"] + bbox["width"] / 2, bbox["y"] + bbox["height"] / 2)
    page.wait_for_timeout(700)


def type_into_element(page: "Page", element: dict[str, Any], text: str) -> None:
    click_element(page, element)
    page.keyboard.insert_text(text)
    page.wait_for_timeout(300)


def print_probe_help() -> None:
    print(
        """
Probe 指令：
  help                         顯示這份說明
  targets                      顯示要校準的 target key
  list                         重新列出目前頁面互動元素
  set <target> <index>          把某個元素記錄成 target
  click <index>                 點擊某個元素，然後重新掃描
  type <index> <text>           點擊某個元素並輸入文字
  press <key>                   送出鍵盤按鍵，例如 Enter 或 Escape
  shot                          截圖
  done                         結束 probe 並輸出報告

建議流程：
  1. set sidebar_toggle <編號>
  2. click <sidebar 編號>
  3. list
  4. set new_conversation <編號>
  5. click <new conversation 編號>
  6. list
  7. set prompt_input <編號>
  8. set send_button <編號>
  9. set attach_button <編號>
"""
    )


def interactive_probe(
    page: "Page",
    output_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    choices: dict[str, Any] = {}
    action_log: list[dict[str, Any]] = []
    elements = extract_elements(page)
    print_elements(elements)
    print_probe_help()

    while True:
        raw = input("probe> ").strip()
        if not raw:
            continue
        parts = raw.split(maxsplit=2)
        command = parts[0].lower()

        if command == "help":
            print_probe_help()
            continue

        if command == "targets":
            print("\n可校準 targets：")
            for key, description in TARGETS:
                status = "done" if choices.get(key) else "pending"
                print(f"- {key}: {description} ({status})")
            continue

        if command == "list":
            elements = extract_elements(page)
            print_elements(elements)
            continue

        if command == "set":
            if len(parts) < 3:
                print("用法：set <target> <index>")
                continue
            target, raw_index = parts[1], parts[2]
            if target not in TARGET_DESCRIPTIONS:
                print(f"未知 target：{target}。輸入 targets 查看可用名稱。")
                continue
            if not raw_index.isdigit():
                print("index 必須是數字。")
                continue
            index = int(raw_index)
            if index < 0 or index >= len(elements):
                print("index 超出目前元素清單範圍。")
                continue
            record_choice(choices, target, index, elements[index])
            action_log.append({"action": "set", "target": target, "index": index})
            continue

        if command == "click":
            if len(parts) < 2 or not parts[1].isdigit():
                print("用法：click <index>")
                continue
            index = int(parts[1])
            if index < 0 or index >= len(elements):
                print("index 超出目前元素清單範圍。")
                continue
            click_element(page, elements[index])
            action_log.append({"action": "click", "index": index, "label": element_label(elements[index])})
            elements = extract_elements(page)
            print_elements(elements)
            continue

        if command == "type":
            if len(parts) < 3 or not parts[1].isdigit():
                print("用法：type <index> <text>")
                continue
            index = int(parts[1])
            if index < 0 or index >= len(elements):
                print("index 超出目前元素清單範圍。")
                continue
            type_into_element(page, elements[index], parts[2])
            action_log.append({"action": "type", "index": index, "text": parts[2]})
            elements = extract_elements(page)
            print_elements(elements)
            continue

        if command == "press":
            if len(parts) < 2:
                print("用法：press <key>")
                continue
            page.keyboard.press(parts[1])
            page.wait_for_timeout(700)
            action_log.append({"action": "press", "key": parts[1]})
            elements = extract_elements(page)
            print_elements(elements)
            continue

        if command == "shot":
            screenshot_path = output_dir / f"tgenie_probe_manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            action_log.append({"action": "shot", "path": str(screenshot_path)})
            print(f"已截圖：{screenshot_path}")
            continue

        if command == "done":
            return elements, choices, action_log

        print("未知指令。輸入 help 查看可用指令。")


def write_report(
    output_dir: Path,
    url: str,
    elements: list[dict[str, Any]],
    choices: dict[str, Any],
    action_log: list[dict[str, Any]],
    screenshot_path: Path | None,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"tgenie_probe_{timestamp}.json"
    md_path = output_dir / f"tgenie_probe_{timestamp}.md"

    payload = {
        "url": url,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "screenshot": str(screenshot_path) if screenshot_path else None,
        "choices": choices,
        "action_log": action_log,
        "elements": elements,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# tGenie Probe Report",
        "",
        f"- URL: `{url}`",
        f"- Screenshot: `{screenshot_path}`" if screenshot_path else "- Screenshot: not captured",
        "",
        "## 校準結果",
        "",
    ]
    for key, description in TARGETS:
        choice = choices.get(key)
        if not choice:
            lines.append(f"- **{key}** ({description}): skipped")
            continue
        lines.append(
            f"- **{key}** ({description}): `{choice['selector_hint']}` — {element_label(choice['element'])}"
        )

    lines.extend(["", "## 操作紀錄", ""])
    if action_log:
        for action in action_log:
            lines.append(f"- `{action}`")
    else:
        lines.append("- No actions recorded.")

    lines.extend(["", "## 互動元素清單", ""])
    for index, element in enumerate(elements):
        bbox = element["bbox"]
        lines.append(
            f"{index}. `{element['tag']}` role=`{element.get('role') or '-'}` "
            f"type=`{element.get('type') or '-'}` "
            f"box=`{bbox['x']},{bbox['y']},{bbox['width']}x{bbox['height']}` "
            f"label={element_label(element)}"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe tGenie UI elements with system Chrome.")
    parser.add_argument("--url", help="tGenie URL. If omitted, the script prompts for it.")
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=default_atlas_config_dir() / "chrome-profile",
        help="Chrome user data directory. Default: user Atlas config directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("probe-output"),
        help="Directory for probe reports. Default: ./probe-output",
    )
    parser.add_argument("--no-screenshot", action="store_true", help="Do not capture a screenshot.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    url = args.url or os.environ.get("ATLAS_TGENIE_URL") or input("tGenie URL：").strip()
    if not url:
        print("缺少 tGenie URL。")
        return 2

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        print("缺少 Playwright。請先安裝專案依賴：python -m pip install -e .")
        return 2

    args.profile_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(args.profile_dir),
            channel="chrome",
            headless=False,
            viewport=None,
            args=["--start-maximized"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url, wait_until="domcontentloaded")

        print("\nChrome 已開啟。請完成登入，並停在 tGenie 主對話頁。")
        input("完成後回到 terminal 按 Enter 繼續 probe...")

        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except PlaywrightTimeoutError:
            pass

        screenshot_path: Path | None = None
        if not args.no_screenshot:
            screenshot_path = args.output_dir / f"tgenie_probe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            page.screenshot(path=str(screenshot_path), full_page=True)

        elements, choices, action_log = interactive_probe(page, args.output_dir)
        json_path, md_path = write_report(args.output_dir, url, elements, choices, action_log, screenshot_path)

        print("\nProbe 完成。輸出檔案：")
        print(f"- {json_path}")
        print(f"- {md_path}")
        if screenshot_path:
            print(f"- {screenshot_path}")

        context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
