#!/usr/bin/env python3
"""Generate LastCan state fixtures for screen inspection. Today: 2026-06-09."""
import copy
import json
import os
from datetime import date, timedelta

TODAY = date(2026, 6, 9)
OUT = "/tmp/lastcan-states"
os.makedirs(OUT, exist_ok=True)


def iso(d):
    return d.isoformat()


def base():
    return {
        "version": 3,
        "onboarding": {"complete": False, "ageConfirmed": False, "stepIndex": 0},
        "profile": {
            "substance": "dip",
            "method": "cold",
            "goal": "quit",
            "brand": "",
            "strengthMg": 0,
            "perDay": 5,
            "years": 8,
            "weeklyCost": 42,
            "triggers": [],
            "whyDriver": None,
            "startDate": iso(TODAY),
            "quitDate": None,
        },
        "pledges": [],
        "logs": [],
        "vault": [],
        "sosSessions": [],
        "subscription": {"isPro": False, "plan": None, "renewsAt": None},
        "reminders": {
            "enabled": True,
            "dailyPromise": True,
            "dailyPromiseHour": 8,
            "triggerNudges": False,
            "milestones": True,
            "quietHoursStart": 22,
            "quietHoursEnd": 7,
        },
        "meta": {
            "paywallSeen": False,
            "lastCelebratedMilestoneId": None,
            "bestStreak": 0,
            "priorCleanDays": 0,
        },
        "createdAt": 1780000000000,
    }


def write(name, state):
    with open(f"{OUT}/{name}.json", "w") as f:
        json.dump(state, f)


# --- Onboarding resume states (age confirmed, progressively filled) ---------
def onb(step, **profile_patch):
    s = base()
    s["onboarding"] = {"complete": False, "ageConfirmed": True, "stepIndex": step}
    s["profile"].update(profile_patch)
    return s


write("onb-step2-substance", onb(2))
write("onb-step3-usage", onb(3))
write("onb-step4-triggers", onb(4, triggers=["meals", "driving", "stress"]))
write("onb-step5-why", onb(5, triggers=["meals", "driving", "stress"], whyDriver="family"))
write("onb-step6-method", onb(6, triggers=["meals", "driving", "stress"], whyDriver="family"))
write("onb-step7-build", onb(7, triggers=["meals", "driving", "stress"], whyDriver="family", method="taper"))
write("onb-step8-reveal", onb(8, triggers=["meals", "driving", "stress"], whyDriver="family", method="taper"))
write(
    "onb-step9-commit",
    onb(
        9,
        triggers=["meals", "driving", "stress"],
        whyDriver="family",
        method="cold",
        quitDate=iso(TODAY),
    ),
)

# --- Day one: just finished onboarding, empty everything --------------------
s = base()
s["onboarding"] = {"complete": True, "ageConfirmed": True, "stepIndex": 9}
s["profile"].update(
    triggers=["meals", "driving", "stress"],
    whyDriver="family",
    method="cold",
    startDate=iso(TODAY),
    quitDate=iso(TODAY),
)
s["meta"]["paywallSeen"] = True
write("day1-fresh", s)

# --- Day 12, free tier, cold turkey, lived-in --------------------------------
s = base()
start = TODAY - timedelta(days=12)
s["onboarding"] = {"complete": True, "ageConfirmed": True, "stepIndex": 9}
s["profile"].update(
    triggers=["meals", "driving", "stress"],
    whyDriver="family",
    method="cold",
    startDate=iso(start),
    quitDate=iso(start),
)
s["pledges"] = [iso(start + timedelta(days=i)) for i in range(12)]  # not yet today
s["logs"] = [
    {"id": "log_1", "date": iso(start + timedelta(days=2)), "amount": 1, "trigger": "stress", "at": 1781000000000},
]
s["vault"] = [
    {"id": "vault_1", "kind": "reason", "title": "My kids never see me with a lip in", "pinned": True, "createdAt": 1781000000000},
    {"id": "vault_2", "kind": "letter", "title": "A letter to future me", "body": "If you are reading this, you wanted to quit badly enough to write it down. Remember the morning cough, the hiding tins in the truck. Hold the line.", "createdAt": 1781000001000},
    {"id": "vault_3", "kind": "savingsGoal", "title": "Fishing kayak", "amount": 1200, "createdAt": 1781000002000},
]
s["sosSessions"] = [
    {"id": "sos_1", "at": 1781200000000, "outcome": "made-it"},
    {"id": "sos_2", "at": 1781300000000, "outcome": "made-it"},
    {"id": "sos_3", "at": 1781100000000, "outcome": "slipped"},
]
s["meta"].update(paywallSeen=True, bestStreak=12, lastCelebratedMilestoneId="dip-1w")
write("day12-free", s)

# --- Day 5, Pro, taper plan ---------------------------------------------------
s = base()
start = TODAY - timedelta(days=5)
s["onboarding"] = {"complete": True, "ageConfirmed": True, "stepIndex": 9}
s["profile"].update(
    substance="pouches",
    perDay=10,
    strengthMg=6,
    weeklyCost=35,
    triggers=["work", "coffee", "boredom"],
    whyDriver="health",
    method="taper",
    startDate=iso(start),
    quitDate=None,
)
s["pledges"] = [iso(start + timedelta(days=i)) for i in range(5)]
s["logs"] = [
    {"id": "log_t1", "date": iso(TODAY), "amount": 1, "trigger": "coffee", "at": 1781400000000},
    {"id": "log_t2", "date": iso(TODAY), "amount": 1, "trigger": "work", "at": 1781410000000},
    {"id": "log_t3", "date": iso(TODAY - timedelta(days=1)), "amount": 6, "at": 1781300000000},
]
s["subscription"] = {"isPro": True, "plan": "annual", "renewsAt": "2027-06-04"}
s["meta"].update(paywallSeen=True, bestStreak=5)
write("day5-pro-taper", s)

print("wrote fixtures to", OUT)
