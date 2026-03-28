"""
Shared constants for the prospecting pipeline.
Import from here instead of duplicating across modules.
"""

# Best niches for GBP quick-close sales
PRIME_NICHES = [
    "plumbers", "HVAC contractors", "electricians",
    "auto repair shops", "roofers", "general contractors",
    "dentists", "chiropractors", "hair salons", "barber shops",
    "landscapers", "pest control", "cleaning services",
]

# Mid-size US cities — lots of small businesses, lower competition
TARGET_CITIES = [
    "Houston TX", "Phoenix AZ", "San Antonio TX", "Dallas TX",
    "Jacksonville FL", "Austin TX", "Columbus OH", "Charlotte NC",
    "Indianapolis IN", "Fort Worth TX", "Memphis TN", "Louisville KY",
    "Tucson AZ", "Fresno CA", "Sacramento CA", "Mesa AZ",
    "Kansas City MO", "Albuquerque NM", "Atlanta GA", "Tampa FL",
]

# Hard quality gate for sales pipeline: do not add businesses above this score.
MAX_PROSPECT_SCORE = 5.0

# Hard niche gate for sales pipeline.
# Any requested niche outside this allow-list will be blocked or normalized.
ALLOWED_TARGET_NICHES = [
    "general_service",
    "plumbers",
    "locksmiths",
    "electricians",
    "hvac contractors",
    "roofers",
    "landscapers",
    "cabinet installers",
    "driveway renovation specialists",
    "garage door",
    "towing",
    "pest control",
    "cleaning services",
    "painters",
    "flooring contractors",
    "concrete contractors",
    "remodelers",
    "tree services",
    "fence contractors",
    "pool services",
    "junk removal",
]

DEFAULT_TARGET_NICHE = "general_service"
