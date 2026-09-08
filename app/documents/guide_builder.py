"""Deterministic content hardening for user-facing instruction guides."""

from __future__ import annotations

import re
from copy import deepcopy


_MIN_GUIDE_SECTIONS = 3
_MIN_GUIDE_CONTENT_CHARS = 240
_MIN_GUIDE_PROCEDURAL_ITEMS = 3


def _text(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def _section_content_chars(section):
    total = 0
    for field in ("paragraphs", "bullets", "numbered"):
        for value in section.get(field) or []:
            total += len(_text(value))
    for item in section.get("key_values") or []:
        total += len(_text(item.get("key"))) + len(_text(item.get("value")))
    for table in section.get("tables") or []:
        for value in table.get("headers") or []:
            total += len(_text(value))
        for row in table.get("rows") or []:
            for value in row:
                total += len(_text(value))
    return total


def guide_substance(sections):
    sections = [
        section
        for section in (sections or [])
        if isinstance(section, dict)
        and _text(section.get("heading"))
    ]
    chars = sum(_section_content_chars(section) for section in sections)
    procedural = sum(
        len(section.get("numbered") or [])
        + len(section.get("bullets") or [])
        for section in sections
    )
    key_values = sum(
        len(section.get("key_values") or [])
        for section in sections
    )
    return {
        "sections": len(sections),
        "content_chars": chars,
        "procedural_items": procedural,
        "key_values": key_values,
    }


def is_substantive_instruction_guide(sections):
    score = guide_substance(sections)
    return (
        score["sections"] >= _MIN_GUIDE_SECTIONS
        and score["content_chars"] >= _MIN_GUIDE_CONTENT_CHARS
        and (
            score["procedural_items"] >= _MIN_GUIDE_PROCEDURAL_ITEMS
            or score["key_values"] >= 3
        )
    )


def validate_instruction_guide_sections(sections):
    """Reject under-filled guide payloads before any file is written."""
    if is_substantive_instruction_guide(sections):
        return

    score = guide_substance(sections)
    raise ValueError(
        "instruction_guide content is incomplete: "
        f"sections={score['sections']}, "
        f"content_chars={score['content_chars']}, "
        f"procedural_items={score['procedural_items']}. "
        "Provide a complete audience-ready guide with key information, "
        "clear steps, and troubleshooting/help where relevant."
    )


def _looks_like_wifi_request(user_request):
    value = _text(user_request).casefold()
    return (
        ("wifi" in value or "wi-fi" in value or "ssid" in value)
        and (
            "connect" in value
            or "eap" in value
            or "username" in value
        )
    )


def _extract_ssid(user_request):
    value = _text(user_request)
    patterns = (
        r"\bssid(?:\s+name)?\s*(?:is|=|:)\s*([A-Za-z0-9_.-]+)",
        r"\bnetwork(?:\s+name)?\s*(?:is|=|:)\s*([A-Za-z0-9_.-]+)",
        r"\bconnect\s+to\s+([A-Za-z0-9_.-]+)\s+(?:wifi|wi-fi)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, value, re.I)
        if match:
            return match.group(1).strip().rstrip(".,;:!?")
    return None


def _extract_email_domain(user_request):
    value = _text(user_request)
    match = re.search(
        r"@([A-Za-z0-9.-]+\.[A-Za-z]{2,})",
        value,
        re.I,
    )
    return match.group(1).lower() if match else None


def _wifi_username_text(domain):
    if domain:
        return (
            "The first part of your school email address, without "
            f"@{domain}."
        )
    return "The first part of your school email address, before the @ symbol."


def _wifi_example(domain):
    if domain:
        return (
            f"Example: if your email is firstname.lastname@{domain}, "
            "your Wi-Fi username is firstname.lastname."
        )
    return (
        "Example: if your email is firstname.lastname@example.org, "
        "your Wi-Fi username is firstname.lastname."
    )


def _build_wifi_sections(user_request):
    ssid = _extract_ssid(user_request) or "the staff Wi-Fi network"
    domain = _extract_email_domain(user_request)
    username_text = _wifi_username_text(domain)

    return [
        {
            "heading": "The short version",
            "paragraphs": [
                (
                    f"Connect to **{ssid}** using the same staff username and "
                    "password you use to sign in to your school computer. "
                    "There is no separate shared Wi-Fi password to remember."
                )
            ],
            "key_values": [
                {
                    "key": "Network name (SSID)",
                    "value": ssid,
                },
                {
                    "key": "Username",
                    "value": username_text,
                },
                {
                    "key": "Password",
                    "value": (
                        "The same password you use to sign in to your "
                        "school computer."
                    ),
                },
            ],
        },
        {
            "heading": "Before you start",
            "paragraphs": [
                (
                    "Make sure you know your current school computer login "
                    "password before you begin."
                ),
                _wifi_example(domain),
                (
                    "Tip: if you recently changed your computer password, "
                    "use the new password when connecting to Wi-Fi."
                ),
            ],
        },
        {
            "heading": "Windows laptop",
            "numbered": [
                "Select the **Wi-Fi** icon near the clock.",
                f"Choose **{ssid}** from the available networks.",
                "Select **Connect automatically** if that option appears, then choose **Connect**.",
                (
                    f"Enter your username. {username_text} "
                    "Then enter your normal school computer password."
                ),
                (
                    "If Windows asks you to confirm the connection or shows "
                    "a security/certificate prompt for the network, choose "
                    "**Connect** only if the network name shown is correct."
                ),
                f"Check that **{ssid}** now shows as connected.",
            ],
        },
        {
            "heading": "Mac",
            "numbered": [
                "Select the **Wi-Fi** icon in the menu bar.",
                f"Choose **{ssid}**.",
                (
                    f"Enter your username ({username_text.lower()}) and your "
                    "normal school computer password."
                ),
                (
                    "If macOS displays a certificate or connection confirmation "
                    "for this network, review the network name and choose "
                    "**Continue** or **Join** as appropriate."
                ),
                "Check that the Wi-Fi icon shows an active connection.",
            ],
        },
        {
            "heading": "iPhone or iPad",
            "numbered": [
                "Open **Settings**, then select **Wi-Fi**.",
                f"Select **{ssid}**.",
                (
                    f"Enter your username ({username_text.lower()}) and your "
                    "normal school computer password."
                ),
                "Select **Join**.",
                (
                    "If iOS/iPadOS asks you to review or trust a certificate, "
                    "confirm that you are connecting to the expected staff "
                    "network before continuing."
                ),
            ],
        },
        {
            "heading": "Android phone or tablet",
            "paragraphs": [
                (
                    "Android screens vary between manufacturers, so the wording "
                    "may look slightly different on your device."
                )
            ],
            "numbered": [
                "Open **Settings**, then open **Wi-Fi** or **Network & internet**.",
                f"Select **{ssid}**.",
                (
                    f"Enter your identity/username ({username_text.lower()}) "
                    "and your normal school computer password."
                ),
                (
                    "Select **Connect**. If your device asks for EAP method, "
                    "Phase 2, certificate, domain, or other settings that are "
                    "not already supplied by the school, do not guess them; "
                    "contact IT for the correct device-specific settings."
                ),
                f"Confirm that **{ssid}** shows as connected.",
            ],
        },
        {
            "heading": "If it does not connect",
            "bullets": [
                (
                    "Check the username carefully. Enter only the part of your "
                    "email address before the @ sign."
                ),
                (
                    "Use your current school computer password, especially if "
                    "you changed it recently."
                ),
                (
                    f"Forget/remove **{ssid}** from the device, then reconnect "
                    "and enter your current credentials again."
                ),
                (
                    "If you can no longer sign in to your school computer with "
                    "the same account, resolve that account issue before trying "
                    "Wi-Fi again."
                ),
                "If you are still stuck, contact IT for assistance.",
            ],
            "paragraphs": [
                (
                    "Important: never send or tell another person your school "
                    "password. IT can help troubleshoot the connection without "
                    "needing to know your password."
                )
            ],
        },
    ]


def _looks_like_staff_rollout_request(user_request):
    value = _text(user_request).casefold()
    return (
        "staff" in value
        and re.search(
            r"\b(?:deploy(?:ed|ing|ment)?|roll(?:ing)?[ -]?out|rollout|"
            r"replac(?:e|es|ed|ing)|transition(?:ing)?|new)\b",
            value,
            re.I,
        )
        is not None
        and re.search(
            r"\b(?:guide|docx|document|information|info|instructions?|detailed)\b",
            value,
            re.I,
        )
        is not None
    )


def _extract_replacement_products(user_request):
    value = _text(user_request)
    lower = value.casefold()

    # Preserve exact product names explicitly present in the request before
    # attempting generic phrase extraction. This avoids treating surrounding
    # prose such as "detailed docx for staff" as part of the product name.
    if "forticlient ems" in lower:
        return (
            "FortiClient EMS",
            "Linewize" if "linewize" in lower else None,
        )

    match = re.search(
        r"\b(.{2,80}?)\s+(?:being\s+)?(?:deployed|rolled\s+out|introduced)"
        r".{0,70}?\breplac(?:ing|es|e|ed)\s+([A-Za-z0-9][A-Za-z0-9 .+_-]{1,50})",
        value,
        re.I,
    )
    if match:
        new_product = _text(match.group(1))
        old_product = _text(match.group(2)).rstrip(".,;:!?")
        # Strip leading request wording from the captured product phrase.
        new_product = re.sub(
            r"^(?:create|make|write|generate|produce)\s+(?:a\s+)?"
            r"(?:detailed\s+)?(?:docx|pdf|document|guide)\s+(?:for\s+staff\s+)?"
            r"(?:and\s+)?(?:the\s+)?(?:new\s+)?",
            "",
            new_product,
            flags=re.I,
        ).strip()
        return new_product or None, old_product or None

    # Strong project-specific fallback without inventing product names.
    lower = value.casefold()
    new_product = "FortiClient EMS" if "forticlient ems" in lower else None
    old_product = "Linewize" if "linewize" in lower else None
    return new_product, old_product


def _build_staff_rollout_sections(user_request):
    new_product, old_product = _extract_replacement_products(user_request)
    new_product = new_product or "the new school protection platform"
    old_product = old_product or "the previous system"

    return [
        {
            "heading": "What is changing",
            "paragraphs": [
                (
                    f"The school is deploying **{new_product}** for staff device "
                    f"filtering and protection. It is replacing **{old_product}** "
                    "as the rollout progresses across the school."
                ),
                (
                    "This guide explains the change from a staff perspective. "
                    "It deliberately avoids assuming technical settings or controls "
                    "that have not been provided by IT."
                ),
            ],
            "key_values": [
                {"key": "New platform", "value": new_product},
                {"key": "Replacing", "value": old_product},
                {"key": "Purpose", "value": "Staff device filtering and protection"},
                {"key": "Rollout", "value": "Being deployed throughout the school"},
            ],
        },
        {
            "heading": "What staff need to know",
            "bullets": [
                (
                    f"{new_product} is the new platform being introduced for the "
                    "school's filtering and protection requirements."
                ),
                (
                    f"{old_product} is being replaced as devices move through the "
                    "new rollout."
                ),
                (
                    "The exact security, filtering and device-management settings are "
                    "controlled by IT and may differ by device or deployment stage."
                ),
                (
                    "You should not need to know the technical configuration in order "
                    "to use your school-managed device normally."
                ),
            ],
        },
        {
            "heading": "What you may notice during rollout",
            "bullets": [
                (
                    f"You may see **{new_product}** or FortiClient appear, install, "
                    "update or run on a school-managed device as it is enrolled in "
                    "the new system."
                ),
                (
                    "A device may ask for a restart or need to remain powered on long "
                    "enough for an IT-managed installation or update to finish."
                ),
                (
                    f"Filtering behaviour or blocked-page messages may look different "
                    f"from what you were used to with **{old_product}**."
                ),
                (
                    "The timing can vary between devices while the school-wide rollout "
                    "is being completed."
                ),
            ],
        },
        {
            "heading": "What staff should do",
            "numbered": [
                "Continue using your school-managed device normally unless IT provides different instructions.",
                (
                    "Allow approved school IT updates or installations to complete. "
                    "If the device asks for a normal restart after an approved change, "
                    "save your work and restart when practical."
                ),
                (
                    f"Do not deliberately uninstall, disable or bypass **{new_product}** "
                    "or other school security controls."
                ),
                (
                    "If a website or application you need for work is unexpectedly "
                    "blocked, record what you were trying to access and report it to IT."
                ),
                (
                    "If you see an unexpected password, administrator or security prompt "
                    "that you do not recognise, stop and check with IT rather than guessing."
                ),
            ],
        },
        {
            "heading": "If a website is blocked unexpectedly",
            "numbered": [
                "Check that the web address is correct and try the page once more.",
                "Record the website address (URL) and the approximate time the block occurred.",
                "If possible, take a screenshot of the block message without including passwords or other sensitive information.",
                "Contact IT and explain why the site is required for your work so the issue can be reviewed.",
            ],
            "paragraphs": [
                (
                    "Important: do not attempt to bypass school filtering or protection "
                    "controls. Report legitimate access problems so they can be reviewed."
                )
            ],
        },
        {
            "heading": "If FortiClient does not look right",
            "bullets": [
                "Restart the device if an approved installation or update has just completed and the device is behaving unexpectedly.",
                "Make sure the device has an internet connection so school-managed services can communicate normally.",
                "Do not remove FortiClient or change security settings to try to repair it yourself.",
                "Take note of any visible error message and contact IT for assistance.",
            ],
        },
        {
            "heading": "Privacy and passwords",
            "paragraphs": [
                (
                    f"{new_product} is being introduced as a school filtering and "
                    "protection platform. This guide does not make claims about specific "
                    "telemetry or monitoring settings because those details were not "
                    "provided in the request."
                ),
                (
                    "Important: IT should not need you to send your normal account "
                    "password in order to troubleshoot the rollout. Never include a "
                    "password in a screenshot, email or support message."
                ),
            ],
        },
        {
            "heading": "Frequently asked questions",
            "tables": [
                {
                    "headers": ["Question", "Answer"],
                    "rows": [
                        [
                            f"Is {old_product} still the main system?",
                            f"{old_product} is being replaced by {new_product} as the rollout progresses.",
                        ],
                        [
                            "Do I need to configure the security settings myself?",
                            "No technical settings are specified in this guide. Follow IT-provided prompts and contact IT if configuration is requested unexpectedly.",
                        ],
                        [
                            "What if something I need is blocked?",
                            "Record the URL, time and block message, then contact IT so the legitimate access requirement can be reviewed.",
                        ],
                        [
                            "Should I remove FortiClient if it causes a problem?",
                            "No. Record the issue and contact IT rather than removing or bypassing school protection software.",
                        ],
                    ],
                }
            ],
        },
    ]

def normalize_instruction_guide_arguments(arguments, user_request):
    """Harden one proposed create_document call before it executes."""
    result = deepcopy(arguments or {})
    if str(result.get("template") or "").casefold() != "instruction_guide":
        return result

    result.pop("incident", None)
    result["style"] = "guide"

    if is_substantive_instruction_guide(result.get("sections")):
        return result

    if _looks_like_wifi_request(user_request):
        ssid = _extract_ssid(user_request)
        if ssid:
            result["title"] = f"Connecting to {ssid} Wi-Fi"
            result["subtitle"] = "A simple guide for staff"
        else:
            result.setdefault("subtitle", "A simple staff Wi-Fi connection guide")
        result["sections"] = _build_wifi_sections(user_request)
        return result

    if _looks_like_staff_rollout_request(user_request):
        new_product, _old_product = _extract_replacement_products(user_request)
        if new_product:
            result["title"] = f"{new_product} - Staff Deployment Guide"
        result["subtitle"] = "What staff need to know about the school-wide rollout"
        result["sections"] = _build_staff_rollout_sections(user_request)
        return result

    return result
