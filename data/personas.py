from datetime import date

SEED = 42

START = date(2026, 4, 1)
END = date(2026, 9, 30)
VALID_START = date(2026, 8, 1)
TEST_START = date(2026, 9, 1)
DEMO_TODAY = date(2026, 10, 8)

EID_WINDOWS = [(date(2026, 5, 17), date(2026, 5, 27))]

OUT_TYPES = ["send_money", "cash_out", "merchant_payment", "bill_payment", "mobile_recharge"]
IN_TYPES = ["cash_in", "receive_money", "salary_in"]

CATEGORIES = [
    "groceries",
    "eating_out",
    "transport",
    "shopping",
    "health",
    "education",
    "rent",
    "family_support",
    "personal_transfer",
    "electricity",
    "gas",
    "water",
    "internet",
    "mobile_recharge",
    "savings",
    "business_supplies",
    "cash_withdrawal",
    "other",
]

DISCRETIONARY = ["eating_out", "shopping", "transport"]

MERCHANT_TYPES = [
    "none",
    "grocery",
    "restaurant",
    "transport",
    "online_shop",
    "pharmacy",
    "education",
    "wholesale",
    "telecom",
    "utility",
    "bank",
]

COUNTERPARTY_TYPES = ["person", "merchant", "biller", "agent", "operator", "employer"]

MERCHANT_CATEGORY = {
    "grocery": "groceries",
    "restaurant": "eating_out",
    "transport": "transport",
    "online_shop": "shopping",
    "pharmacy": "health",
    "education": "education",
    "wholesale": "business_supplies",
    "telecom": "mobile_recharge",
}

MERCHANT_NAMES = {
    "grocery": ["Shapla General Store", "Notun Bazar Mart", "Rahman Store", "Sobuj Grocery", "Mayer Doa Store", "Poribar Mart", "Kacha Bazar Shop", "Jononi Traders"],
    "restaurant": ["Biryani Ghor", "Cha Adda", "Kabab Corner", "Bhorta Bari", "Dhaba Express", "Mishti Mukh", "Fuchka Point", "Tehari House", "Burger Adda", "Khichuri Kitchen"],
    "transport": ["City Ride", "Nogor Bus Counter", "Rail Ticket Counter", "Jatri Ride", "Launch Ticket Desk"],
    "online_shop": ["Deshi Cart", "Gadget Hut", "Rong Fashion", "Boi Ghor Online", "Ghor Sajai", "Style Bazar"],
    "pharmacy": ["Shefa Pharmacy", "Niramoy Pharma", "Arogya Medicine Corner"],
    "education": ["Alo Coaching Centre", "Proshikkhon Academy", "City College Accounts"],
    "wholesale": ["Bondhon Wholesale", "Chawk Traders", "Mohajon Supply", "Bikroy Distributors"],
}

OPERATORS = ["Operator A", "Operator B", "Operator C"]

BILLERS = {
    "electricity": ("B-ELEC", "City Electric Supply"),
    "gas": ("B-GAS", "Metro Gas"),
    "water": ("B-WATER", "City Water Authority"),
    "internet": ("B-NET", "FiberLink Internet"),
    "savings": ("B-DPS", "Shonchoy DPS"),
}

ELECTRICITY_SEASON = {4: 1.0, 5: 1.08, 6: 1.14, 7: 1.14, 8: 1.1, 9: 1.04, 10: 0.96}

EID_BOOST = {"shopping": 2.0, "groceries": 1.5, "eating_out": 1.2, "transport": 1.4}

PERSON_NAMES = [
    "Abdur", "Nasrin", "Jahid", "Sumaiya", "Rakib", "Farzana", "Imran", "Mitu", "Sohel", "Shirin",
    "Babul", "Tania", "Mamun", "Laboni", "Rubel", "Poly", "Hasib", "Nipa", "Arif", "Jesmin",
    "Shanto", "Ruma", "Faisal", "Keya", "Sabbir", "Lima", "Masud", "Sharmin", "Nayeem", "Rupa",
]

PURPOSES = {
    "family_support": {"category": "family_support", "scam_story": False},
    "rent": {"category": "rent", "scam_story": False},
    "friend": {"category": "personal_transfer", "scam_story": False},
    "purchase": {"category": "shopping", "scam_story": False},
    "business": {"category": "business_supplies", "scam_story": False},
    "refund_mistake": {"category": "other", "scam_story": True},
    "prize_fee": {"category": "other", "scam_story": True},
    "agent_request": {"category": "other", "scam_story": True},
    "other": {"category": "other", "scam_story": False},
}

CATEGORY_PURPOSE = {
    "family_support": "family_support",
    "rent": "rent",
    "personal_transfer": "friend",
    "shopping": "purchase",
    "business_supplies": "business",
}

SCAM_TYPES = ["refund_scam", "prize_fee", "fake_agent_call", "account_takeover", "impersonation"]

MODEST_SCAM_SHARE = 0.3
PURPOSE_HONESTY_SCALE = 1.0

SCAM_PURPOSE = {
    "refund_scam": ("refund_mistake", 0.75),
    "prize_fee": ("prize_fee", 0.65),
    "fake_agent_call": ("agent_request", 0.60),
    "account_takeover": (None, 0.0),
    "impersonation": (None, 0.0),
}

HOURS = {
    "meal": [0, 0, 0, 0, 0, 0, 0, 1, 2, 1, 1, 2, 6, 8, 5, 2, 2, 3, 4, 7, 9, 8, 4, 1],
    "shop": [0, 0, 0, 0, 0, 0, 1, 2, 4, 6, 7, 6, 4, 3, 3, 4, 5, 6, 7, 7, 6, 4, 2, 1],
    "commute": [0, 0, 0, 0, 0, 0, 2, 6, 9, 6, 2, 1, 1, 1, 1, 2, 3, 6, 8, 6, 3, 1, 1, 0],
    "day": [0, 0, 0, 0, 0, 0, 1, 2, 4, 6, 7, 7, 6, 5, 5, 6, 6, 6, 5, 5, 4, 3, 2, 1],
    "evening": [1, 0, 0, 0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 3, 3, 3, 4, 5, 6, 8, 9, 9, 7, 3],
    "late": [4, 2, 1, 0, 0, 0, 0, 0, 1, 1, 2, 3, 4, 4, 4, 4, 4, 5, 6, 7, 8, 9, 9, 7],
    "night": [9, 9, 9, 8, 6, 4, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 5],
}

PERSONAS = {
    "salaried": {
        "count": 80,
        "income": (26000, 62000),
        "income_ref": 42000,
        "payday": (1, 5),
        "hold": (0.35, 1.2),
        "p_late": 0.05,
        "p_topup": 0.8,
        "new_cp": 0.10,
        "scam_rate": 0.26,
        "scam_mix": {"refund_scam": 0.35, "prize_fee": 0.13, "fake_agent_call": 0.22, "account_takeover": 0.18, "impersonation": 0.12},
        "unusual_rate": 0.28,
        "bills": {"electricity": (0.85, 1500, 3200), "gas": (0.6, 1080, 1080), "water": (0.5, 450, 900), "internet": (0.8, 600, 1200), "savings": (0.3, 1000, 5000)},
        "recurring": {"rent": (0.55, 0.26, 0.36), "family_support": (0.6, 0.08, 0.18)},
        "spend": [
            ("groceries", "merchant_payment", "grocery", 2.2, 650, 0.5, "shop"),
            ("eating_out", "merchant_payment", "restaurant", 2.6, 360, 0.4, "meal"),
            ("transport", "merchant_payment", "transport", 3.0, 150, 0.5, "commute"),
            ("shopping", "merchant_payment", "online_shop", 0.45, 1400, 0.6, "evening"),
            ("shopping", "send_money", "none", 0.12, 1800, 0.6, "evening"),
            ("health", "merchant_payment", "pharmacy", 0.3, 520, 0.6, "day"),
            ("mobile_recharge", "mobile_recharge", "telecom", 1.0, 100, 0.6, "day"),
            ("personal_transfer", "send_money", "none", 0.6, 900, 0.7, "evening"),
            ("cash_withdrawal", "cash_out", "none", 0.35, 3000, 0.5, "day"),
        ],
    },
    "student": {
        "count": 50,
        "income": (6000, 14000),
        "income_ref": 9000,
        "payday": (1, 8),
        "hold": (0.6, 1.4),
        "p_late": 0.1,
        "p_topup": 0.45,
        "new_cp": 0.15,
        "scam_rate": 0.3,
        "scam_mix": {"refund_scam": 0.27, "prize_fee": 0.35, "fake_agent_call": 0.08, "account_takeover": 0.18, "impersonation": 0.12},
        "unusual_rate": 0.22,
        "bills": {"internet": (0.45, 400, 800)},
        "recurring": {"rent": (0.5, 0.3, 0.45)},
        "spend": [
            ("eating_out", "merchant_payment", "restaurant", 3.2, 180, 0.45, "late"),
            ("transport", "merchant_payment", "transport", 2.4, 90, 0.5, "commute"),
            ("shopping", "merchant_payment", "online_shop", 0.35, 750, 0.6, "late"),
            ("shopping", "send_money", "none", 0.15, 900, 0.6, "late"),
            ("education", "merchant_payment", "education", 0.2, 1200, 0.6, "day"),
            ("groceries", "merchant_payment", "grocery", 0.8, 260, 0.5, "shop"),
            ("mobile_recharge", "mobile_recharge", "telecom", 1.4, 60, 0.6, "late"),
            ("personal_transfer", "send_money", "none", 1.1, 350, 0.7, "late"),
            ("cash_withdrawal", "cash_out", "none", 0.3, 1500, 0.5, "day"),
        ],
    },
    "shop_owner": {
        "count": 30,
        "income": (60000, 160000),
        "income_ref": 100000,
        "payday": (1, 1),
        "hold": (0.25, 0.6),
        "p_late": 0.08,
        "p_topup": 0.85,
        "new_cp": 0.12,
        "scam_rate": 0.28,
        "scam_mix": {"refund_scam": 0.4, "prize_fee": 0.08, "fake_agent_call": 0.22, "account_takeover": 0.18, "impersonation": 0.12},
        "unusual_rate": 0.3,
        "bills": {"electricity": (0.9, 2500, 6000), "internet": (0.5, 800, 1500), "water": (0.3, 500, 1200)},
        "recurring": {"rent": (0.8, 0.1, 0.2)},
        "spend": [
            ("business_supplies", "merchant_payment", "wholesale", 2.4, 6500, 0.55, "day"),
            ("business_supplies", "send_money", "none", 1.2, 4500, 0.6, "day"),
            ("cash_withdrawal", "cash_out", "none", 2.6, 6000, 0.5, "evening"),
            ("groceries", "merchant_payment", "grocery", 1.2, 700, 0.5, "shop"),
            ("eating_out", "merchant_payment", "restaurant", 1.0, 300, 0.45, "meal"),
            ("transport", "merchant_payment", "transport", 1.0, 200, 0.5, "commute"),
            ("mobile_recharge", "mobile_recharge", "telecom", 1.2, 120, 0.6, "day"),
            ("personal_transfer", "send_money", "none", 0.5, 1500, 0.7, "evening"),
            ("family_support", "send_money", "none", 0.25, 5000, 0.5, "day"),
        ],
    },
    "irregular": {
        "count": 40,
        "income": (9000, 20000),
        "income_ref": 14000,
        "payday": (1, 1),
        "hold": (0.15, 0.45),
        "p_late": 0.3,
        "p_topup": 0.3,
        "new_cp": 0.12,
        "scam_rate": 0.32,
        "scam_mix": {"refund_scam": 0.31, "prize_fee": 0.31, "fake_agent_call": 0.08, "account_takeover": 0.18, "impersonation": 0.12},
        "unusual_rate": 0.2,
        "bills": {"internet": (0.15, 400, 600)},
        "recurring": {},
        "spend": [
            ("cash_withdrawal", "cash_out", "none", 2.2, 1200, 0.6, "evening"),
            ("family_support", "send_money", "none", 0.6, 2000, 0.6, "evening"),
            ("mobile_recharge", "mobile_recharge", "telecom", 2.0, 40, 0.6, "evening"),
            ("groceries", "merchant_payment", "grocery", 0.9, 320, 0.5, "shop"),
            ("eating_out", "merchant_payment", "restaurant", 0.7, 130, 0.5, "meal"),
            ("transport", "merchant_payment", "transport", 0.8, 80, 0.5, "commute"),
            ("personal_transfer", "send_money", "none", 0.5, 500, 0.7, "evening"),
            ("health", "merchant_payment", "pharmacy", 0.15, 300, 0.6, "day"),
        ],
    },
}

DEMO_CUSTOMERS = [
    {"customer_id": "D0001", "name": "Rina Akter", "persona": "salaried", "language": "en"},
    {"customer_id": "D0002", "name": "Tanvir Hasan", "persona": "student", "language": "en", "start_balance": 6500},
    {"customer_id": "D0003", "name": "Karim Uddin", "persona": "shop_owner", "language": "bn", "start_balance": 38000},
    {"customer_id": "D0004", "name": "Salma Begum", "persona": "irregular", "language": "bn", "start_balance": 4200},
]

RINA = {
    "income": 45000,
    "payday": 1,
    "hold": 1.5,
    "p_late": 0.0,
    "p_topup": 1.0,
    "new_cp": 0.03,
    "scam_rate": 0.0,
    "unusual_rate": 0.0,
    "bills": {
        "internet": {"day": 8, "amount": 1050, "variable": False},
        "electricity": {"day": 10, "amount": 2500, "variable": True},
        "savings": {"day": 12, "amount": 3000, "variable": False},
        "gas": {"day": 15, "amount": 1080, "variable": False},
        "water": {"day": 20, "amount": 620, "variable": True},
    },
    "recurring": {
        "rent": {"day": 3, "amount": 15000},
        "family_support": {"day": 5, "amount": 8000},
    },
    "spend": [
        ("groceries", "merchant_payment", "grocery", 2.2, 650, 0.4, "shop"),
        ("eating_out", "merchant_payment", "restaurant", 4.0, 375, 0.12, "meal", [0, 2, 4, 5]),
        ("transport", "merchant_payment", "transport", 3.0, 150, 0.4, "commute"),
        ("shopping", "merchant_payment", "online_shop", 0.4, 1300, 0.5, "evening"),
        ("health", "merchant_payment", "pharmacy", 0.25, 480, 0.5, "day"),
        ("mobile_recharge", "mobile_recharge", "telecom", 0.8, 100, 0.4, "day"),
        ("personal_transfer", "send_money", "none", 1.6, 1900, 0.15, "evening"),
    ],
    "electricity_script": {7: 2480, 8: 2560, 9: 2500},
    "start_balance": 10800,
    "week_meals": [(5, 13, 380), (6, 13, 420), (7, 20, 450), (8, 9, 400)],
}
