"""District crosswalk — v2.

Fixes audit findings C-05 (22% of live TB rows discarded, systematically the
post-2011 districts) and M-17 (93 silent fuzzy accepts with no review queue).

The v1 crosswalk was `difflib.get_close_matches(cutoff=0.85)` with no alias
table and no logging of successes. That cannot resolve:
  * post-2011 SPLITS      'nandyal' is a 2022 child of Kurnool
  * RENAMES               'dharashiv' IS Osmanabad; 'ahilyanagar' IS Ahmadnagar
  * SUB-DISTRICT UNITS    'mumbai colaba' is a TB reporting unit, not a district
  * CROSS-STATE FILING    PMJAY files Telangana districts under Andhra Pradesh

None of those have string overlap with their target, so no edit-distance metric
reaches them. They need an explicit table. ALIASES below is that table: every
entry is one reviewed decision with a category, and `resolve_label` never
silently guesses — fuzzy matches are still allowed but are RETURNED for review
rather than applied invisibly.

Resolution order (first hit wins):
  1. exact normalised name match against the state's spine
  2. ALIASES lookup (state, label) -> one or more spine names
  3. suffix/prefix stripping rules (municipal corporations, ' rural', ' hp')
  4. fuzzy match at cutoff -> ACCEPTED BUT FLAGGED for the review file
  5. unresolved -> reported, never dropped silently

Category semantics, all recorded on every mapping:
  RENAME       same territory, new name. 1:1.
  SPLIT_CHILD  post-2011 district carved from a spine parent. n:1, values are
               SUMMED into the parent. This is the correct direction: the spine
               is the 2011/2017 frame, so children roll UP.
  SUBUNIT      sub-district reporting unit (city ward, chest clinic) -> parent.
  CROSS_STATE  filed under the wrong state by the source.
  PRORATE      genuinely ambiguous within a state (Delhi's chest clinics cannot
               be attributed to a district). Distributed across the named
               targets in proportion to population, and flagged.
  DROP         not a district at all ('non functional', 'PSU', 'NHCP').
"""
import re
from difflib import get_close_matches

FUZZY_CUTOFF = 0.88          # raised from v1's 0.85; anything accepted is logged

RENAME, SPLIT_CHILD, SUBUNIT, CROSS_STATE, PRORATE, DROP = (
    "RENAME", "SPLIT_CHILD", "SUBUNIT", "CROSS_STATE", "PRORATE", "DROP")


def norm_name(s):
    s = str(s).lower().strip().replace("&", "and")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


STATE_ALIASES = {
    "nct of delhi": "delhi", "delhi ut": "delhi",
    "jammu and kashmir ut": "jammu and kashmir",
    "andaman and nicobar island": "andaman and nicobar islands",
    "pondicherry": "puducherry", "orissa": "odisha",
    "chattisgarh": "chhattisgarh", "uttaranchal": "uttarakhand",
    # data.gov.in's NFHS-5 factsheet misspells Maharashtra. Left unhandled this
    # silently orphaned all 36 of its districts, including Mumbai and Pune.
    "maharastra": "maharashtra",
    "dadra and nagar haveli and daman and diu": "dadra and nagar haveli",
}


def norm_state(s):
    return STATE_ALIASES.get(norm_name(s), norm_name(s))


# ---------------------------------------------------------------------------
# The alias table.  {(state, source_label): (category, [spine targets])}
# Targets are NORMALISED spine names. validate_aliases() asserts every target
# exists, so a typo here fails loudly instead of silently dropping a district.
# ---------------------------------------------------------------------------
_A = {}


def _add(state, cat, mapping):
    for label, targets in mapping.items():
        _A[(state, label)] = (cat, targets if isinstance(targets, list) else [targets])


# --- Andhra Pradesh: the 2022 reorganisation (13 -> 26 districts) -----------
_add("andhra pradesh", SPLIT_CHILD, {
    "nandyal": "kurnool",
    "eluru": "west godavari",
    "polavaram": "west godavari",
    "kakinada": "east godavari",
    "konaseema": "east godavari",
    "dr b r ambedkar konaseema": "east godavari",
    "ntr": "krishna",
    "anakapalli": "visakhapatanam",
    "alluri sitharama raju": "visakhapatanam",
    "parvathipuram manyam": "vizianagaram",
    "tirupati": "chittoor",
    "sri sathya sai": "anantapur",
    "bapatla": "guntur",
    "palnadu": "guntur",
    "markapuram": "prakasam",
})
_add("andhra pradesh", RENAME, {
    "ananthapuramu": "anantapur",
    "sri potti sriramulu nellore": "spsr nellore",
    "nellor": "spsr nellore",
    "cuddapah": "y s r",
})
# PMJAY files these Telangana districts under Andhra Pradesh.
_add("andhra pradesh", CROSS_STATE, {
    "mahabubnagar": "mahabubnagar", "khammam": "khammam",
    "nalgonda": "nalgonda", "siddipet": "siddipet",
    "nagarkurnool": "nagarkurnool", "sangareddy": "sangareddy",
    "jogulamba gadwal": "jogulamba gadwal", "ranga reddy": "ranga reddy",
})
_CROSS_STATE_TARGET = {"andhra pradesh": "telangana",
                       "jammu and kashmir": "ladakh"}
_add("andhra pradesh", DROP, {"non functional": []})

# --- Telangana --------------------------------------------------------------
_add("telangana", SPLIT_CHILD, {
    "warangal rural": "warangal", "warangal urban": "warangal"})

# --- Chhattisgarh: the 2022 new districts -----------------------------------
_add("chhattisgarh", SPLIT_CHILD, {
    "sakti": "janjgir champa",
    "sarangarh bilaigarh": "raigarh",
    "khairagarh chhuikhadan gandai": "rajnandgaon",
    "khairgarh chhuikhadan gandai": "rajnandgaon",
    "mohla manpur ambagarhchowki": "rajnandgaon",
    "mohla manpur ambagarh chouki": "rajnandgaon",
    "manendragarh chirmiri bharatpur": "korea",
    "manendragarh chirimiri bharatpur": "korea",
})
_add("chhattisgarh", RENAME, {"koriya": "korea", "bijapur cgh": "bijapur"})

# --- Rajasthan: the 2023 new districts --------------------------------------
_add("rajasthan", SPLIT_CHILD, {
    "balotra": "barmer", "beawar": "ajmer", "deeg": "bharatpur",
    "didwana kuchaman": "nagaur", "khairthal tijara": "alwar",
    "kotputli behror": "jaipur", "phalodi": "jodhpur", "salumbar": "udaipur",
})
_add("rajasthan", SUBUNIT, {"jaipur ii": "jaipur"})

# --- Maharashtra ------------------------------------------------------------
_add("maharashtra", RENAME, {
    "ahilyanagar": "ahmednagar",
    "chhatrapati sambhajinagar": "aurangabad",
    "dharashiv": "osmanabad",
    "raigarh mh": "raigad",
})
_add("maharashtra", SUBUNIT, {
    "kalyan dombivli": "thane", "bhiwandi nizampur": "thane",
    "mira bhayander": "thane", "ulhasnagar": "thane", "navi mumbai": "thane",
    "vasai virar": "palghar", "malegaon": "nashik",
    "nanded waghala": "nanded",
    "pimpri chinchwad": "pune", "pune rural": "pune",
})
# Ni-kshay reports Mumbai as ~20 ward-level TB units. Attributing each ward to
# Mumbai City vs Mumbai Suburban would require a ward->district table we do not
# hold, and guessing would corrupt both. They are one metropolitan market, so
# the notifications are distributed across the two districts by population and
# flagged. This is an explicit, reviewable assumption.
_MUMBAI_WARDS = [
    "mumbai andheri east", "mumbai andheri west", "mumbai bail bazar road",
    "mumbai bandra east", "mumbai bandra west", "mumbai borivali",
    "mumbai byculla", "mumbai centenary", "mumbai chembur", "mumbai colaba",
    "mumbai dadar", "mumbai dahisar", "mumbai ghatkopar", "mumbai goregaon",
    "mumbai govandi", "mumbai grant road", "mumbai kandivali", "mumbai kurla",
    "mumbai malad", "mumbai mulund", "mumbai parel", "mumbai prabhadevi",
    "mumbai sion", "mumbai vikhroli",
]
_add("maharashtra", PRORATE,
     {w: ["mumbai", "mumbai suburban"] for w in _MUMBAI_WARDS})

# --- West Bengal ------------------------------------------------------------
_add("west bengal", RENAME, {
    "north 24 parganas": "24 paraganas north",
    "south 24 parganas": "24 paraganas south",
    "paschim medinipur": "medinipur west", "west midnapur": "medinipur west",
    "purba medinipur": "medinipur east", "east midnapur": "medinipur east",
    "dakshin dinajpur": "dinajpur dakshin", "south dinajpur": "dinajpur dakshin",
    "uttar dinajpur": "dinajpur uttar", "north dinajpur": "dinajpur uttar",
    "darjiling": "darjeeling",
})
_add("west bengal", SUBUNIT, {
    "basirhat": "24 paraganas north", "diamond harbour": "24 paraganas south",
    "bishnupur": "bankura", "rampurhat": "birbhum",
    "nandigram hd": "medinipur east",
    "alipore kolkata": "kolkata", "bagbazar kolkata": "kolkata",
    "behala kolkata": "kolkata", "hazi kolkata": "kolkata",
    "maniktala kolkata": "kolkata", "manshatala kolkata": "kolkata",
    "mtmtb kolkata": "kolkata", "strand bank kolkata": "kolkata",
    "tangra kolkata": "kolkata", "tollygunge kolkata": "kolkata",
})

# --- Delhi ------------------------------------------------------------------
_DELHI = ["central", "east", "new delhi", "north", "north east", "north west",
          "shahdara", "south", "south east", "south west", "west"]
_add("delhi", RENAME, {d + " delhi": d for d in _DELHI if d != "new delhi"})
# Ni-kshay's Delhi TB units are chest clinics and named localities with no
# district attribution available. Distributed across Delhi's 11 districts by
# population and flagged.
_add("delhi", PRORATE, {lbl: list(_DELHI) for lbl in [
    "bijwasan", "bjrm chest clinic", "bsa chest clinic", "cd chest clinic",
    "chest clinic narela", "damien foundation india trust", "ddu chest clinic",
    "gtb chest clinic", "gulabi bagh", "hedgewar chest clinic", "jhandewalan",
    "karawal nagar", "kingsway", "ln chest clinic", "mnch chest clinic",
    "moti nagar", "ndmc", "nehru nagar", "nitrd", "patparganj", "rk mission",
    "rtrm chest clinic", "sgm chest clinic", "spm marg", "spmh chest clinic",
]})

# --- Sikkim: renamed 2021 + two new districts -------------------------------
_add("sikkim", RENAME, {
    "east sikkim": "gangtok", "west sikkim": "gyalshing",
    "north sikkim": "mangan", "south sikkim": "namchi",
})
_add("sikkim", SPLIT_CHILD, {"pakyong": "gangtok", "soreng": "gyalshing"})

# --- Tamil Nadu -------------------------------------------------------------
_add("tamil nadu", SUBUNIT, {
    "central chennai": "chennai", "east chennai": "chennai",
    "north chennai": "chennai", "south chennai": "chennai",
    "west chennai": "chennai",
})
_add("tamil nadu", RENAME, {
    "thoothukudi": "tuticorin", "nilgiris": "the nilgiris"})
_add("tamil nadu", SPLIT_CHILD, {"mayiladuthurai": "nagapattinam"})

# --- Uttar Pradesh ----------------------------------------------------------
_add("uttar pradesh", RENAME, {
    "allahabad": "prayagraj", "faizabad": "ayodhya",
    "jyotiba phule nagar": "amroha", "kanshiram nagar": "kasganj",
    "sant ravidas nagar": "bhadohi", "hamirpur up": "hamirpur",
})

# --- Punjab -----------------------------------------------------------------
_add("punjab", RENAME, {
    "firozpur": "ferozepur", "muktsar": "sri muktsar sahib",
    "mansa pn": "mansa", "mohali": "s a s nagar",
    "nawanshahr": "shahid bhagat singh nagar",
})
_add("punjab", SPLIT_CHILD, {"malerkotla": "sangrur"})

# --- the rest ---------------------------------------------------------------
_add("haryana", RENAME, {"gurgaon": "gurugram", "mewat": "nuh"})
_add("gujarat", RENAME, {"dahod": "dohad", "the dangs": "dang"})
_add("gujarat", SUBUNIT, {
    "jamnagar rural": "jamnagar", "surat rural": "surat",
    "vyara": "tapi", "vav tharad": "banas kantha"})
_add("assam", RENAME, {"sibsagar": "sivasagar",
                       "north cachar hill": "dima hasao"})
_add("assam", SPLIT_CHILD, {"bajali": "barpeta", "tamulpur": "baksa"})
_add("bihar", RENAME, {"kaimur": "kaimur bhabua",
                       "east champaran": "purbi champaran",
                       "west champaran": "pashchim champaran"})
_add("madhya pradesh", RENAME, {"hoshangabad": "narmadapuram",
                                "khandwa": "east nimar"})
_add("jharkhand", RENAME, {"purbi singhbhum": "east singhbum",
                           "pashchimi singhbhum": "west singhbhum"})
_add("karnataka", RENAME, {"bengaluru city bbmp": "bengaluru urban"})
_add("karnataka", SPLIT_CHILD, {"vijayanagara": "ballari",
                                "vijayanagar": "ballari"})
_add("jammu and kashmir", RENAME, {"badgam": "budgam", "bandipur": "bandipora"})
_add("jammu and kashmir", CROSS_STATE, {"leh": "leh ladakh", "kargil": "kargil"})
_add("ladakh", RENAME, {"leh": "leh ladakh", "dtc kargil": "kargil"})
_add("himachal pradesh", RENAME, {"bilaspur hp": "bilaspur",
                                  "hamirpur hp": "hamirpur", "una hp": "una"})
_add("odisha", SUBUNIT, {"bhubaneshwar": "khordha"})
_add("puducherry", RENAME, {"puducherry": "pondicherry"})
_add("lakshadweep", RENAME, {"lakshadweep": "lakshadweep district"})
_add("meghalaya", PRORATE, {
    "jaintia hills": ["east jaintia hills", "west jaintia hills"]})
_add("andaman and nicobar islands", PRORATE, {
    "andamans and nicobars": ["nicobars", "north and middle andaman",
                              "south andamans"]})

# --- second pass: labels surfaced by the v2 review file ---------------------
_add("bihar", RENAME, {"aurangabad bi": "aurangabad"})
_add("rajasthan", SUBUNIT, {"jaipur i": "jaipur"})
_add("telangana", RENAME, {"jangaon": "jangoan"})
_add("chhattisgarh", RENAME, {"sarguja": "surguja"})
_add("delhi", RENAME, {"shahadra": "shahdara"})
_add("tamil nadu", RENAME, {"kancheepuram": "kanchipuram"})
_add("jharkhand", RENAME, {"kodarma": "koderma"})
_add("odisha", RENAME, {"sonapur": "sonepur", "debagarh": "deogarh",
                        "baudh": "boudh"})
_add("gujarat", RENAME, {"ahmedabad": "ahmadabad", "aravali": "arvalli",
                         "chhota udaipur": "chhotaudepur"})
# nfhs5_factsheet spelling variants (names-only source, older orthography)
_add("maharashtra", RENAME, {
    "ahmadnagar": "ahmednagar", "bid": "beed", "buldana": "buldhana",
    "gondiya": "gondia"})
_add("karnataka", RENAME, {
    "bangalore": "bengaluru urban", "bangalore rural": "bengaluru rural",
    "belgaum": "belagavi", "bellary": "ballari", "bijapur": "vijayapura",
    "gulbarga": "kalaburagi", "mysore": "mysuru", "chikmagalur": "chikkamagaluru",
    "davanagere": "davangere", "bagalkot": "bagalkote"})
_add("west bengal", RENAME, {
    "haora": "howrah", "hugli": "hooghly", "koch bihar": "coochbehar",
    "north twenty four pargana": "24 paraganas north",
    "south twenty four pargana": "24 paraganas south"})
_add("madhya pradesh", RENAME, {
    "khandwa east nimar": "east nimar", "khargone west nimar": "khargone",
    "narsimhapur": "narsinghpur"})
_add("rajasthan", RENAME, {"chittaurgarh": "chittorgarh", "dhaulpur": "dholpur"})
_add("uttar pradesh", RENAME, {"mahamaya nagar": "hathras"})
_add("uttarakhand", RENAME, {"garhwal": "pauri garhwal"})
_add("chhattisgarh", RENAME, {"kabeerdham": "kabirdham"})
_add("assam", RENAME, {"kamrup metropolitan": "kamrup metro",
                       "morigaon": "marigaon"})
_add("jammu and kashmir", RENAME, {"punch": "poonch", "rajauri": "rajouri"})
_add("sikkim", RENAME, {"east district": "gangtok", "north district": "mangan",
                        "south district": "namchi", "west district": "gyalshing"})
_add("andhra pradesh", RENAME, {"sri potti sriramulu nello": "spsr nellore"})
_add("chhattisgarh", RENAME, {"uttar bastar kanker": "kanker"})
_add("jammu and kashmir", RENAME, {"shupiyan": "shopian"})
_add("karnataka", RENAME, {"shimoga": "shivamogga", "tumkur": "tumakuru"})
_add("maharashtra", RENAME, {"raigarh": "raigad"})
_add("odisha", RENAME, {"subarnapur": "sonepur"})
_add("punjab", RENAME, {"sahibzada ajit singh nagar": "s a s nagar"})
_add("tamil nadu", RENAME, {"thoothukkudi": "tuticorin"})
_add("uttar pradesh", RENAME, {"sant ravidas nagar bhadohi": "bhadohi"})
# The factsheet files Manipur's Chandel under Mizoram — a source error.
_add("mizoram", CROSS_STATE, {"chandel": "chandel"})
_CROSS_STATE_TARGET["mizoram"] = "manipur"

# Aggregate/administrative rows that are not districts.
for _st in ("dadra and nagar haveli", "daman and diu", "nhcp", "psu"):
    _add(_st, DROP, {"whole state": []})
# PMJAY lists central-government hospital pools as pseudo-districts.
_add("nhcp", DROP, {"nhcp": []})
for _lbl in ["esic", "nhcp", "ndmc", "mo ayush", "mo chemicals and fertilizers",
             "mo civil aviation", "mo commerce and industry", "mo defense",
             "mo finance", "mo health and family welfare",
             "mo heavy industries and public enterprises", "mo home affairs",
             "mo human resource development", "mo jal shakti", "mo mines",
             "mo minority affairs", "mo petroleum and natural gas", "mo power",
             "mo railways", "mo science and technology", "mo shipping",
             "mo social justice and empowerment", "mo steel"]:
    for _st in ("psu", "nhcp", "delhi"):
        _add(_st, DROP, {_lbl: []})
# UTs with no spine row of their own.
for _st in ("dadra and nagar haveli", "daman and diu"):
    for _lbl in ("dadra and nagar haveli", "daman", "diu"):
        _add(_st, DROP, {_lbl: []})

ALIASES = _A

# Suffix rules applied before fuzzy matching.
_SUFFIX_RE = re.compile(
    r"\s+(mc|municipal corporation|corporation|mcorp|urban|rural)$")


def validate_aliases(spine_names_by_state):
    """Assert every alias target exists in the spine. Returns a list of
    problems; an empty list means the table is internally consistent."""
    problems = []
    for (state, label), (cat, targets) in ALIASES.items():
        if cat == DROP:
            continue
        lookup_state = _CROSS_STATE_TARGET.get(state, state) if cat == CROSS_STATE else state
        names = spine_names_by_state.get(lookup_state, set())
        for t in targets:
            if t not in names:
                problems.append((state, label, cat, t, "target not in spine"))
    return problems


def resolve_label(state, label, spine_names_by_state, strip_suffix=True):
    """Resolve one source label to spine target(s).

    Returns (targets, category, detail). `targets` is a list of normalised
    spine names; empty means unresolved or deliberately dropped.
    """
    st = norm_state(state)
    lab = norm_name(label)
    names = spine_names_by_state.get(st, set())

    if lab in names:
        return [lab], "EXACT", None

    def _alias(key):
        hit = ALIASES.get((st, key))
        if not hit:
            return None
        cat, targets = hit
        if cat == DROP:
            return [], DROP, "not a district"
        if cat == CROSS_STATE:
            return list(targets), cat, _CROSS_STATE_TARGET.get(st, st)
        return list(targets), cat, None

    got = _alias(lab)
    if got is not None:
        return got

    # Suffix stripping must run BEFORE the fuzzy fallback AND must re-enter the
    # alias table: 'Ahilyanagar MC' strips to 'ahilyanagar', which is a RENAME
    # of Ahmadnagar. v2's first pass checked aliases only on the unstripped
    # label and left 27 municipal-corporation rows unresolved.
    if strip_suffix:
        stripped = lab
        for _ in range(3):                     # 'ahmedabad municipal corporation'
            nxt = _SUFFIX_RE.sub("", stripped).strip()
            if nxt == stripped:
                break
            stripped = nxt
        if stripped != lab:
            if stripped in names:
                return [stripped], "SUFFIX", lab[len(stripped):].strip()
            got = _alias(stripped)
            if got is not None:
                return got[0], "SUFFIX+" + got[1], stripped
            cand = get_close_matches(stripped, sorted(names), n=1,
                                     cutoff=FUZZY_CUTOFF)
            if cand:
                return [cand[0]], "SUFFIX+FUZZY", cand[0]

    cand = get_close_matches(lab, sorted(names), n=1, cutoff=FUZZY_CUTOFF)
    if cand:
        return [cand[0]], "FUZZY", cand[0]

    return [], "UNRESOLVED", None
