# src/slack_bot.py
from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from csv_loader import load_validated_frames, teachers_from_df, classes_from_df
from db import get_con, init_db

from cover_store import CoverStore
from cover_repo import insert_cover, get_cover, fill_cover

from recommendations_engine import get_recommendations_for_cover
from time_fmt import fmt_local_range

from accept_service import attempt_accept

from indexes import (
    index_regular_classes_by_teacher,
    index_filled_cover_classes_by_teacher,
    merge_busy_maps,
)

from cover_message_repo import upsert_cover_message, get_cover_message
from cover_dm_repo import (
    upsert_dm,
    set_status,
    list_dms_for_cover,
    list_declined_teacher_ids,
)

from reason_library import match_reasons

load_dotenv()

ASSETS_DIR = Path("assets")

teachers_df, classes_df = load_validated_frames(ASSETS_DIR)
TEACHERS_BY_ID = teachers_from_df(teachers_df)
CLASSES_BY_ID = classes_from_df(classes_df)

TEACHER_ID_BY_SLACK = {
    t.slack_user_id: t.teacher_id for t in TEACHERS_BY_ID.values() if t.slack_user_id
}

COORDINATOR_SLACK_IDS = {
    x.strip()
    for x in os.environ.get("COORDINATOR_SLACK_IDS", "").split(",")
    if x.strip()
}
COORDINATOR_CHANNEL_ID = os.environ.get("COORDINATOR_CHANNEL_ID", "").strip()
PUBLIC_COVERS_CHANNEL_ID = os.environ["PUBLIC_COVERS_CHANNEL_ID"].strip()

app = App(token=os.environ["SLACK_BOT_TOKEN"])


# ----------------------------
# Small helpers
# ----------------------------
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_coordinator(slack_user_id: str) -> bool:
    return slack_user_id in COORDINATOR_SLACK_IDS


def codes_to_bullets(codes: list[str]) -> str:
    if not codes:
        return "Not eligible."
    lines = [f"• {match_reasons(c)}" for c in codes]
    return "\n".join(lines)


def split_reason_str(reason_str: str) -> list[str]:
    if not reason_str:
        return []
    return reason_str.split("|")


def dm_teacher(
    client, slack_user_id: str, text: str, blocks: list[dict]
) -> tuple[str, str]:
    im = client.conversations_open(users=slack_user_id)
    dm_channel_id = im["channel"]["id"]
    resp = client.chat_postMessage(channel=dm_channel_id, text=text, blocks=blocks)
    return dm_channel_id, resp["ts"]


# ----------------------------
# Admin message pointer (stored in DB)
# ----------------------------
def upsert_admin_message(con, cover_id: str, channel_id: str, message_ts: str) -> None:
    con.execute(
        """
        INSERT INTO cover_admin_messages (cover_id, channel_id, message_ts)
        VALUES (?, ?, ?)
        ON CONFLICT(cover_id) DO UPDATE SET
          channel_id=excluded.channel_id,
          message_ts=excluded.message_ts
        """,
        (cover_id, channel_id, message_ts),
    )


def get_admin_message(con, cover_id: str) -> tuple[str, str] | None:
    cur = con.execute(
        "SELECT channel_id, message_ts FROM cover_admin_messages WHERE cover_id=?",
        (cover_id,),
    )
    row = cur.fetchone()
    return (row[0], row[1]) if row else None


# ----------------------------
# Blocks
# ----------------------------
def frozen_blocks(text: str) -> list[dict]:
    return [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]


def teacher_dm_blocks(cover_id: str, c) -> list[dict]:
    when = fmt_local_range(c.start_at, c.end_at)
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Cover available*\n"
                    f"*Class:* `{c.class_id}`\n"
                    f"*Campus:* {c.campus.title()}\n"
                    f"*When:* {when} (Sydney time)"
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Accept"},
                    "style": "primary",
                    "action_id": "accept_cover",
                    "value": json.dumps({"cover_id": cover_id}),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Decline"},
                    "action_id": "decline_cover",
                    "value": json.dumps({"cover_id": cover_id}),
                },
            ],
        },
    ]


def public_cover_blocks(cover, declined_count: int) -> list[dict]:
    c = CLASSES_BY_ID[cover.class_id]
    when = fmt_local_range(c.start_at, c.end_at)

    if cover.status == "FILLED" and cover.assigned_teacher_id:
        winner = TEACHERS_BY_ID.get(cover.assigned_teacher_id)
        winner_name = winner.full_name if winner else cover.assigned_teacher_id
        status_line = f"*Status:* FILLED ({winner_name})"
    else:
        status_line = "*Status:* OPEN"

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Cover {cover.cover_id}"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Class:* `{c.class_id}`\n"
                    f"*Campus:* {c.campus.title()}\n"
                    f"*When:* {when} (Sydney time)\n"
                    f"{status_line}\n"
                    f"*Declined:* {declined_count}"
                ),
            },
        },
    ]

    if cover.status == "OPEN":
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Accept"},
                        "style": "primary",
                        "action_id": "accept_cover",
                        "value": json.dumps({"cover_id": cover.cover_id}),
                    }
                ],
            }
        )

    return blocks


def admin_cover_blocks(
    cover,
    recommended_ids: list[str],
    dm_status_by_teacher: dict[str, str],
    declined_ids: set[str],
) -> list[dict]:
    c = CLASSES_BY_ID[cover.class_id]
    when = fmt_local_range(c.start_at, c.end_at)

    if cover.status == "FILLED" and cover.assigned_teacher_id:
        winner = TEACHERS_BY_ID.get(cover.assigned_teacher_id)
        winner_name = winner.full_name if winner else cover.assigned_teacher_id
        status_line = f"*Status:* FILLED ({winner_name})"
    else:
        status_line = "*Status:* OPEN"

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Coordinator panel — {cover.cover_id}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Class:* `{c.class_id}`\n"
                    f"*Campus:* {c.campus.title()}\n"
                    f"*When:* {when} (Sydney time)\n"
                    f"{status_line}\n"
                    f"*Declined:* {len(declined_ids)}"
                ),
            },
        },
        {"type": "divider"},
    ]

    # If filled, no notify / assign controls
    if cover.status != "OPEN":
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "This cover is filled. Notifications are closed.",
                },
            }
        )
        return blocks

    # Controls row
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Notify all (recommended)"},
                    "action_id": "notify_all",
                    "value": json.dumps({"cover_id": cover.cover_id}),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Manual assign"},
                    "action_id": "open_assign_modal",
                    "value": json.dumps({"cover_id": cover.cover_id}),
                },
            ],
        }
    )

    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Recommended teachers*"},
        }
    )

    if not recommended_ids:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "No recommended teachers found."},
            }
        )
        return blocks

    shown = 0
    for tid in recommended_ids:
        t = TEACHERS_BY_ID.get(tid)
        if not t:
            continue

        status = dm_status_by_teacher.get(tid, "")
        status_tag = ""
        if tid in declined_ids:
            status_tag = " — DECLINED"
        elif status:
            status_tag = f" — {status}"

        # Keep listing visible even after notified; only remove controls when filled.
        if tid in declined_ids:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{t.full_name}* (`{tid}`){status_tag}",
                    },
                }
            )
        else:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{t.full_name}* (`{tid}`){status_tag}",
                    },
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Notify"},
                        "action_id": "notify_teacher",
                        "value": json.dumps(
                            {"cover_id": cover.cover_id, "teacher_id": tid}
                        ),
                    },
                }
            )

        shown += 1
        if shown >= 15:
            break

    return blocks


# ----------------------------
# Message updaters
# ----------------------------
def update_public_cover_card(client, con, cover_id: str) -> None:
    cover = get_cover(con, cover_id)
    if not cover:
        return

    ptr = get_cover_message(con, cover_id)
    if not ptr:
        return

    declined = list_declined_teacher_ids(con, cover_id)
    channel_id, msg_ts = ptr

    client.chat_update(
        channel=channel_id,
        ts=msg_ts,
        text=f"Cover {cover_id}",
        blocks=public_cover_blocks(cover, declined_count=len(declined)),
    )


def update_admin_cover_card(client, con, cover_id: str) -> None:
    cover = get_cover(con, cover_id)
    if not cover:
        return

    ptr = get_admin_message(con, cover_id)
    if not ptr:
        return

    channel_id, msg_ts = ptr

    res = get_recommendations_for_cover(con, cover_id, TEACHERS_BY_ID, CLASSES_BY_ID)
    declined = list_declined_teacher_ids(con, cover_id)

    dm_rows = list_dms_for_cover(con, cover_id)
    dm_status_by_teacher = {r["teacher_id"]: r["status"] for r in dm_rows}

    client.chat_update(
        channel=channel_id,
        ts=msg_ts,
        text=f"Coordinator panel {cover_id}",
        blocks=admin_cover_blocks(
            cover, res.recommended, dm_status_by_teacher, declined
        ),
    )


def update_all_cover_cards(client, con, cover_id: str) -> None:
    update_public_cover_card(client, con, cover_id)
    update_admin_cover_card(client, con, cover_id)


# ----------------------------
# Busy map (regular + filled covers)
# ----------------------------
def build_busy_map(con) -> dict[str, list[Any]]:
    regular_map = index_regular_classes_by_teacher(CLASSES_BY_ID)
    filled_map = index_filled_cover_classes_by_teacher(con, CLASSES_BY_ID)
    return merge_busy_maps(regular_map, filled_map)


# ----------------------------
# Commands
# ----------------------------
@app.command("/cover-create")
def cover_create(ack, command, client, respond):
    ack()

    creator = command["user_id"]
    origin_channel = command["channel_id"]

    if not is_coordinator(creator):
        # respond is fine here (slash commands)
        respond("Not authorised.")
        return

    class_id = command.get("text", "").strip()
    if not class_id:
        respond("Usage: `/cover-create <class_id>`")
        return
    if class_id not in CLASSES_BY_ID:
        respond(f"Unknown class_id: `{class_id}`")
        return

    con = get_con()
    init_db(con)

    store = CoverStore.new()
    cover = store.create_cover(class_id)
    cover_id = insert_cover(con, cover)

    cover_row = get_cover(con, cover_id)
    declined = list_declined_teacher_ids(con, cover_id)

    # ✅ Public message ALWAYS goes to the designated public channel
    posted = client.chat_postMessage(
        channel=PUBLIC_COVERS_CHANNEL_ID,
        text=f"Cover {cover_id}",
        blocks=public_cover_blocks(cover_row, declined_count=len(declined)),
    )
    upsert_cover_message(con, cover_id, posted["channel"], posted["ts"])

    # Admin panel in coordinator channel (or DM fallback)
    res = get_recommendations_for_cover(con, cover_id, TEACHERS_BY_ID, CLASSES_BY_ID)

    dm_rows = list_dms_for_cover(con, cover_id)
    dm_status_by_teacher = {r["teacher_id"]: r["status"] for r in dm_rows}

    admin_blocks = admin_cover_blocks(
        cover_row, res.recommended, dm_status_by_teacher, declined
    )

    if COORDINATOR_CHANNEL_ID:
        admin_post = client.chat_postMessage(
            channel=COORDINATOR_CHANNEL_ID,
            text=f"Coordinator panel {cover_id}",
            blocks=admin_blocks,
        )
        upsert_admin_message(con, cover_id, admin_post["channel"], admin_post["ts"])
    else:
        dm_channel_id, dm_ts = dm_teacher(
            client, creator, f"Coordinator panel {cover_id}", admin_blocks
        )
        upsert_admin_message(con, cover_id, dm_channel_id, dm_ts)

    con.commit()

    # ✅ Confirm to the coordinator without posting noise in channels
    # If they ran it somewhere else, tell them where it actually posted.
    if origin_channel != PUBLIC_COVERS_CHANNEL_ID:
        client.chat_postEphemeral(
            channel=origin_channel,
            user=creator,
            text=f"Created cover `{cover_id}` for `{class_id}`. Posted publicly in the covers channel.",
        )
        # respond to close the slash command nicely
        respond("Done.")
    else:
        respond(f"Created cover `{cover_id}` for `{class_id}`.")


# ----------------------------
# Notify actions (coordinator only)
# ----------------------------
@app.action("notify_teacher")
def notify_teacher_action(ack, body, client):
    ack()

    if not is_coordinator(body["user"]["id"]):
        _safe_feedback(client, body, "Not authorised.")
        return

    payload = json.loads(body["actions"][0]["value"])
    cover_id = payload["cover_id"]
    teacher_id = payload["teacher_id"]

    con = get_con()
    init_db(con)

    cover = get_cover(con, cover_id)
    if not cover:
        _safe_feedback(client, body, "Cover not found.")
        return
    if cover.status != "OPEN":
        _safe_feedback(client, body, "Cover is already filled.")
        update_all_cover_cards(client, con, cover_id)
        return

    t = TEACHERS_BY_ID.get(teacher_id)
    if not t or not t.slack_user_id:
        _safe_feedback(client, body, "Teacher has no Slack user linked.")
        return

    c = CLASSES_BY_ID[cover.class_id]
    blocks = teacher_dm_blocks(cover_id, c)

    dm_channel_id, dm_ts = dm_teacher(
        client, t.slack_user_id, f"Cover {cover_id}", blocks
    )
    upsert_dm(
        con, cover_id, teacher_id, dm_channel_id, dm_ts, "NOTIFIED", utc_now_iso()
    )
    con.commit()

    # Update the panel (this keeps it visible)
    update_admin_cover_card(client, con, cover_id)

    # Confirmation that does NOT replace the panel
    _safe_feedback(client, body, f"Notification sent to {t.full_name}.")


@app.action("notify_all")
def notify_all_action(ack, body, client):
    ack()

    if not is_coordinator(body["user"]["id"]):
        _safe_feedback(client, body, "Not authorised.")
        return

    cover_id = json.loads(body["actions"][0]["value"])["cover_id"]

    con = get_con()
    init_db(con)

    cover = get_cover(con, cover_id)
    if not cover:
        _safe_feedback(client, body, "Cover not found.")
        return
    if cover.status != "OPEN":
        _safe_feedback(client, body, "Cover is already filled.")
        update_all_cover_cards(client, con, cover_id)
        return

    res = get_recommendations_for_cover(con, cover_id, TEACHERS_BY_ID, CLASSES_BY_ID)
    declined = list_declined_teacher_ids(con, cover_id)
    existing = {r["teacher_id"]: r["status"] for r in list_dms_for_cover(con, cover_id)}

    c = CLASSES_BY_ID[cover.class_id]
    ts = utc_now_iso()

    sent = 0
    skipped = 0

    for tid in res.recommended[:25]:
        if tid in declined:
            skipped += 1
            continue
        if existing.get(tid) in {"NOTIFIED", "DECLINED", "ACCEPTED", "LOST"}:
            skipped += 1
            continue

        t = TEACHERS_BY_ID.get(tid)
        if not t or not t.slack_user_id:
            skipped += 1
            continue

        blocks = teacher_dm_blocks(cover_id, c)
        dm_channel_id, dm_ts = dm_teacher(
            client, t.slack_user_id, f"Cover {cover_id}", blocks
        )
        upsert_dm(con, cover_id, tid, dm_channel_id, dm_ts, "NOTIFIED", ts)
        sent += 1

    con.commit()
    update_admin_cover_card(client, con, cover_id)

    _safe_feedback(client, body, f"Notified {sent}. Skipped {skipped}.")


def _safe_feedback(client, body, text: str) -> None:
    """
    Sends a confirmation without replacing the message the user clicked on.
    In channels: ephemeral.
    In DMs: normal message.
    """
    channel_id = body["channel"]["id"]
    user_id = body["user"]["id"]

    if channel_id.startswith("D"):
        client.chat_postMessage(channel=channel_id, text=text)
    else:
        client.chat_postEphemeral(channel=channel_id, user=user_id, text=text)


@app.action("notify_all")
def notify_all_action(ack, body, client, respond):
    ack()

    if not is_coordinator(body["user"]["id"]):
        respond("Not authorised.")
        return

    cover_id = json.loads(body["actions"][0]["value"])["cover_id"]

    con = get_con()
    init_db(con)

    cover = get_cover(con, cover_id)
    if not cover:
        respond("Cover not found.")
        return
    if cover.status != "OPEN":
        respond("Cover is already filled.")
        update_all_cover_cards(client, con, cover_id)
        return

    res = get_recommendations_for_cover(con, cover_id, TEACHERS_BY_ID, CLASSES_BY_ID)
    declined = list_declined_teacher_ids(con, cover_id)
    existing = {r["teacher_id"]: r["status"] for r in list_dms_for_cover(con, cover_id)}

    c = CLASSES_BY_ID[cover.class_id]
    ts = utc_now_iso()

    sent = 0
    skipped = 0

    for tid in res.recommended[:25]:
        if tid in declined:
            skipped += 1
            continue
        if existing.get(tid) in {"NOTIFIED", "DECLINED", "ACCEPTED", "LOST"}:
            skipped += 1
            continue

        t = TEACHERS_BY_ID.get(tid)
        if not t or not t.slack_user_id:
            skipped += 1
            continue

        blocks = teacher_dm_blocks(cover_id, c)
        dm_channel_id, dm_ts = dm_teacher(
            client, t.slack_user_id, f"Cover {cover_id}", blocks
        )
        upsert_dm(con, cover_id, tid, dm_channel_id, dm_ts, "NOTIFIED", ts)
        sent += 1

    con.commit()
    update_admin_cover_card(client, con, cover_id)
    respond(f"Notified {sent}. Skipped {skipped}.")


# ----------------------------
# Manual assign (coordinator modal)
# ----------------------------
@app.action("open_assign_modal")
def open_assign_modal(ack, body, client, respond):
    ack()

    if not is_coordinator(body["user"]["id"]):
        respond("Not authorised.")
        return

    cover_id = json.loads(body["actions"][0]["value"])["cover_id"]

    client.views_open(
        trigger_id=body["trigger_id"],
        view={
            "type": "modal",
            "callback_id": "assign_modal",
            "title": {"type": "plain_text", "text": "Manual assign"},
            "submit": {"type": "plain_text", "text": "Assign"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "private_metadata": json.dumps({"cover_id": cover_id}),
            "blocks": [
                {
                    "type": "input",
                    "block_id": "assign_teacher",
                    "label": {"type": "plain_text", "text": "Select teacher"},
                    "element": {
                        "type": "external_select",
                        "action_id": "assign_teacher_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Search by name or ID",
                        },
                        "min_query_length": 0,
                    },
                }
            ],
        },
    )


@app.options("assign_teacher_select")
def assign_teacher_options(ack, body):
    query = (body.get("value") or "").strip().lower()

    def matches(t) -> bool:
        if not query:
            return True
        return query in t.teacher_id.lower() or query in t.full_name.lower()

    options = []
    for t in TEACHERS_BY_ID.values():
        if matches(t):
            options.append(
                {
                    "text": {
                        "type": "plain_text",
                        "text": f"{t.full_name} ({t.teacher_id})",
                    },
                    "value": t.teacher_id,
                }
            )
        if len(options) >= 100:
            break

    ack(options=options)


@app.view("assign_modal")
def assign_modal_submit(ack, body, client, view):
    ack()

    if not is_coordinator(body["user"]["id"]):
        return

    meta = json.loads(view.get("private_metadata", "{}"))
    cover_id = meta["cover_id"]

    state = view["state"]["values"]
    teacher_id = state["assign_teacher"]["assign_teacher_select"]["selected_option"][
        "value"
    ]

    con = get_con()
    init_db(con)

    # Fill cover atomically
    con.execute("BEGIN IMMEDIATE")
    try:
        cover = get_cover(con, cover_id)
        if not cover or cover.status != "OPEN":
            con.commit()
            update_all_cover_cards(client, con, cover_id)
            return

        ok = fill_cover(con, cover_id, teacher_id)
        con.commit()
        if not ok:
            update_all_cover_cards(client, con, cover_id)
            return

    except Exception:
        con.rollback()
        raise

    # Notify assigned teacher by DM (and record it)
    t = TEACHERS_BY_ID.get(teacher_id)
    if t and t.slack_user_id:
        c = CLASSES_BY_ID[get_cover(con, cover_id).class_id]
        blocks = frozen_blocks(
            f"You have been assigned to cover `{cover_id}`.\n"
            f"Class: `{c.class_id}`\n"
            f"Campus: {c.campus.title()}\n"
            f"When: {fmt_local_range(c.start_at, c.end_at)} (Sydney time)"
        )
        dm_channel_id, dm_ts = dm_teacher(
            client, t.slack_user_id, f"Cover {cover_id} assigned", blocks
        )
        upsert_dm(
            con, cover_id, teacher_id, dm_channel_id, dm_ts, "ACCEPTED", utc_now_iso()
        )
        con.commit()

    # Update any other notified teachers
    winner_name = t.full_name if t else teacher_id
    ts = utc_now_iso()
    for row in list_dms_for_cover(con, cover_id):
        tid = row["teacher_id"]
        ch = row["dm_channel_id"]
        mts = row["dm_ts"]
        status = row["status"]

        if tid == teacher_id:
            continue
        if status == "DECLINED":
            continue

        client.chat_update(
            channel=ch,
            ts=mts,
            text="Cover filled",
            blocks=frozen_blocks(
                f"Cover `{cover_id}` has been filled ({winner_name})."
            ),
        )
        set_status(con, cover_id, tid, "LOST", ts)

    con.commit()
    update_all_cover_cards(client, con, cover_id)

    # Coordinator notification in panel thread if we have it
    ptr = get_admin_message(con, cover_id)
    if ptr:
        channel_id, msg_ts = ptr
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=msg_ts,
            text=f"Cover `{cover_id}` manually assigned to {winner_name}.",
        )


# ----------------------------
# Decline (teacher DM)
# ----------------------------
@app.action("decline_cover")
def decline_cover_action(ack, body, client, respond):
    ack()

    cover_id = json.loads(body["actions"][0]["value"])["cover_id"]
    slack_user_id = body["user"]["id"]
    teacher_id = TEACHER_ID_BY_SLACK.get(slack_user_id)

    dm_channel_id = body["channel"]["id"]
    dm_ts = body["message"]["ts"]

    # Only meaningful in DMs
    if not dm_channel_id.startswith("D"):
        respond("Decline is only available in the DM notification.")
        return

    con = get_con()
    init_db(con)

    cover = get_cover(con, cover_id)
    if not cover:
        client.chat_update(
            channel=dm_channel_id,
            ts=dm_ts,
            text="Declined",
            blocks=frozen_blocks("Declined. (Cover not found.)"),
        )
        return

    if teacher_id:
        upsert_dm(
            con, cover_id, teacher_id, dm_channel_id, dm_ts, "DECLINED", utc_now_iso()
        )
        con.commit()

    client.chat_update(
        channel=dm_channel_id,
        ts=dm_ts,
        text="Declined",
        blocks=frozen_blocks("Declined."),
    )

    update_all_cover_cards(client, con, cover_id)
    respond("Recorded.")


# ----------------------------
# Accept (public or DM)
# ----------------------------
@app.action("accept_cover")
def accept_cover_action(ack, body, client, respond):
    ack()

    cover_id = json.loads(body["actions"][0]["value"])["cover_id"]
    slack_user_id = body["user"]["id"]
    teacher_id = TEACHER_ID_BY_SLACK.get(slack_user_id)

    channel_id = body["channel"]["id"]
    msg_ts = body["message"]["ts"]
    is_dm = channel_id.startswith("D")

    if not teacher_id:
        if is_dm:
            client.chat_update(
                channel=channel_id,
                ts=msg_ts,
                text="Not linked",
                blocks=frozen_blocks("You are not linked to a Teacher profile yet."),
            )
        else:
            client.chat_postEphemeral(
                channel=channel_id,
                user=slack_user_id,
                text="You are not linked to a Teacher profile yet.",
            )
        return

    con = get_con()
    init_db(con)

    cover = get_cover(con, cover_id)
    if not cover:
        if is_dm:
            client.chat_update(
                channel=channel_id,
                ts=msg_ts,
                text="Not found",
                blocks=frozen_blocks("Cover not found."),
            )
        else:
            client.chat_postEphemeral(
                channel=channel_id, user=slack_user_id, text="Cover not found."
            )
        return

    # Gate by "recommended list" (your rule)
    rec = get_recommendations_for_cover(con, cover_id, TEACHERS_BY_ID, CLASSES_BY_ID)
    if teacher_id not in rec.recommended:
        # Prefer showing specific reasons if present
        reasons = []
        if teacher_id in rec.soft_excluded:
            reasons = rec.soft_excluded[teacher_id]
        elif teacher_id in rec.hard_rejected:
            reasons = rec.hard_rejected[teacher_id]

        msg = "You are not eligible to accept this cover.\n" + codes_to_bullets(reasons)

        if is_dm:
            client.chat_update(
                channel=channel_id,
                ts=msg_ts,
                text="Not eligible",
                blocks=frozen_blocks(msg),
            )
        else:
            client.chat_postEphemeral(channel=channel_id, user=slack_user_id, text=msg)
        return

    # Busy map for deterministic clash check (regular + filled covers)
    busy_map = build_busy_map(con)

    ok, reason_or_msg = attempt_accept(
        con,
        cover_id,
        teacher_id,
        TEACHERS_BY_ID,
        CLASSES_BY_ID,
        busy_map,
    )

    cover = get_cover(con, cover_id)
    if not cover:
        return

    winner_id = cover.assigned_teacher_id
    winner = TEACHERS_BY_ID.get(winner_id) if winner_id else None
    winner_name = winner.full_name if winner else (winner_id or "unknown")

    if ok:
        # If accepted from DM, mark that DM record as accepted
        if is_dm:
            upsert_dm(
                con, cover_id, teacher_id, channel_id, msg_ts, "ACCEPTED", utc_now_iso()
            )
            con.commit()
            client.chat_update(
                channel=channel_id,
                ts=msg_ts,
                text="Accepted",
                blocks=frozen_blocks(
                    f"Accepted. You are assigned to cover `{cover_id}`."
                ),
            )
        else:
            # Accepted from public channel: confirm via ephemeral and DM the winner
            client.chat_postEphemeral(
                channel=channel_id,
                user=slack_user_id,
                text=f"Accepted. You are assigned to cover `{cover_id}`.",
            )

            t = TEACHERS_BY_ID.get(teacher_id)
            if t and t.slack_user_id:
                c = CLASSES_BY_ID[cover.class_id]
                blocks = frozen_blocks(
                    f"Accepted. You are assigned to cover `{cover_id}`.\n"
                    f"Class: `{c.class_id}`\n"
                    f"Campus: {c.campus.title()}\n"
                    f"When: {fmt_local_range(c.start_at, c.end_at)} (Sydney time)"
                )
                dm_channel_id, dm_ts = dm_teacher(
                    client, t.slack_user_id, f"Cover {cover_id} accepted", blocks
                )
                upsert_dm(
                    con,
                    cover_id,
                    teacher_id,
                    dm_channel_id,
                    dm_ts,
                    "ACCEPTED",
                    utc_now_iso(),
                )
                con.commit()

        # Update all other DMs (lost)
        ts = utc_now_iso()
        for row in list_dms_for_cover(con, cover_id):
            tid = row["teacher_id"]
            ch = row["dm_channel_id"]
            mts = row["dm_ts"]
            status = row["status"]

            if tid == teacher_id:
                continue
            if status == "DECLINED":
                continue

            client.chat_update(
                channel=ch,
                ts=mts,
                text="Cover filled",
                blocks=frozen_blocks(
                    f"Cover `{cover_id}` has been filled ({winner_name})."
                ),
            )
            set_status(con, cover_id, tid, "LOST", ts)

        con.commit()

        # Update public + admin panels
        update_all_cover_cards(client, con, cover_id)

        # Coordinator notification in panel thread if we have it
        ptr = get_admin_message(con, cover_id)
        if ptr:
            admin_ch, admin_ts = ptr
            client.chat_postMessage(
                channel=admin_ch,
                thread_ts=admin_ts,
                text=f"Cover `{cover_id}` filled ({winner_name}).",
            )

        return

    # Not accepted
    # attempt_accept gives reason_str like "code|code|code"
    codes = split_reason_str(reason_or_msg)
    msg = (
        "Could not accept.\n" + codes_to_bullets(codes)
        if codes
        else "Could not accept."
    )

    if is_dm:
        client.chat_update(
            channel=channel_id,
            ts=msg_ts,
            text="Could not accept",
            blocks=frozen_blocks(msg),
        )
    else:
        client.chat_postEphemeral(channel=channel_id, user=slack_user_id, text=msg)

    update_all_cover_cards(client, con, cover_id)


if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
