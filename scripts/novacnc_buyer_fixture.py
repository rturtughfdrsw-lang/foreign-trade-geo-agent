"""Independent fictional procurement dossier; no runtime/provider configuration.

All numbers are invented internally consistent TEST data, not engineering
certification. E1 alone is reused byte-for-byte from the historical experiment.
"""
from scripts import accept_seo_task_scope as legacy

TITLE = "How to Choose a CNC Machining Center: A Practical Buyer's Guide"
GOAL = ("SYNTHETIC / TEST ONLY: English CNC machining center buyer guide for export procurement teams: "
        "model selection, spindle tests, material/cycle fit, measured results, RFQ/acceptance and delivery/training/support. "
        "Explain implications, applicability and limits; no engineering approval.")
SUBJECTS = ("Model configuration and selection", "Spindle ratings and test conditions",
            "Material and cutting cycle fit", "Measured results and procurement acceptance", "Delivery training and support")
HEADINGS = ("Machine and application fit", "Procurement and acceptance",
            "Compare configuration and model limits", "Read spindle and cutting trial evidence",
            "Specify representative acceptance tests", "Agree delivery training and support")

# This is an analyst-authored question map, never an inferred semantic verdict.
NEEDS = (
    ("F1", 0, "Model-specific travels, table, combined fixture load, tool interface and configuration", "Compare the workpiece plus fixture envelope and equipment options", ("E2",)),
    ("F2", 1, "Spindle rating, duty, power definition, protocol, loaded versus unloaded conditions", "Separate bench ratings from cutting or production capability", ("E1", "E3")),
    ("F3", 2, "Material, geometry, tool, coolant, cutting cycle and exclusions", "Evaluate which application is represented without promising suitability", ("E4",)),
    ("F4", 3, "Measured features, sample, methods, environment and limits", "Distinguish trial observations from production and tolerance guarantees", ("E3", "E4")),
    ("F5", 0, "Verifiable model differences and conditional selection logic", "Explain shortlist choices and identify untested extrapolations", ("E5",)),
    ("F6", 3, "Enquiry fields, representative acceptance procedure, thresholds, responsibilities and unresolved criteria", "Prepare an RFQ and proposed acceptance schedule for negotiation", ("E6",)),
    ("F7", 4, "Delivery trigger, exclusions, installation, training, response and warranty proposal", "Compare scoped commercial obligations without promising site performance", ("E7",)),
    ("F8", 4, "Document versions, validity, option/model scope and unsupported topics", "Keep applicable records together and disclose unanswered questions", ("E2", "E5", "E7")),
)


def fact(eid, key, subject, attribute, value, unit, conditions, scope, limits, quote):
    """Each row is independently traceable to exact document characters."""
    return dict(evidence_id=eid, fact_id=key, subject=subject, attribute=attribute,
                value=value, unit=unit, test_conditions=conditions, applicable_scope=scope,
                limitations=limits, quote=quote, revision="B-TEST-2026-10-11",
                valid_from="2026-10-11", valid_through="2027-01-09",
                validity_basis="Fictional dossier register only; not actual engineering approval",
                source_owner="FICTIONAL NovaCNC", synthetic_only=True)


def rows():
    out = []
    def add(e, key, subject, attribute, value, unit, conditions, scope, limits, quote):
        out.append(fact(e, key, subject, attribute, value, unit, conditions, scope, limits, quote))
    add("E1", "SPINDLE-LEGACY", "NCX7", "continuous unloaded speed", 7200, "rpm", "NOVA-TEST-7; 20 C; unloaded bench",
        "NCX7 only", "No cutting-load or production guarantee", legacy.load_frozen().active_evidence[0].supplement.content.split("\n")[1])
    out[-1]["revision"] = "retained spindle-v1; original bytes unchanged"
    configurations = (
        ("NCX7", "700 mm X, 450 mm Y and 500 mm Z", [700, 450, 500], "900 mm by 450 mm", [900, 450], 400, 20, 7.5),
        ("NCX10", "1000 mm X, 550 mm Y and 550 mm Z", [1000, 550, 550], "1200 mm by 550 mm", [1200, 550], 650, 24, 11),
    )
    for model, axes, travel, table, table_value, load, tools, power in configurations:
        scope = model + " base configuration; fixture A"
        add("E2", model+"-TRAVEL", model, "axis travels XYZ", travel, "mm", "nominal base configuration; fixture clearance untested", scope,
            "Travel is not usable part envelope", f"SYNTHETIC / TEST ONLY: {model} nominal travels are {axes}; fixture and tool clearance must be checked separately.")
        add("E2", model+"-TABLE", model, "table length and width", table_value, "mm", "nominal table surface", scope,
            "Clamping and overhang not assessed", f"SYNTHETIC / TEST ONLY: {model} table surface is {table}; clamping and overhang need application review.")
        add("E2", model+"-LOAD", model, "combined table load", load, "kg", "centered static workpiece plus fixture", scope,
            "Not an off-center or dynamic cutting-load rating", f"SYNTHETIC / TEST ONLY: {model} proposed table load is {load} kg including fixtures, centered and static; off-center and dynamic loads remain unassessed.")
        add("E2", model+"-TOOLS", model, "magazine positions", tools, "positions", "BT40 base magazine; adjacent-tool occupancy applies", scope,
            "Oversize tools require layout confirmation", f"SYNTHETIC / TEST ONLY: {model} base magazine has {tools} positions with BT40 interface; oversized tool adjacency requires a confirmed magazine layout.")
        add("E3", model+"-POWER", model, "continuous motor nameplate power", power, "kW", "motor nameplate; not measured cutting power", scope,
            "No torque curve or low-speed power conclusion", f"SYNTHETIC / TEST ONLY: {model} continuous motor nameplate is {power} kW; this is not measured cutting power and does not establish a torque curve.")
    add("E2", "OPTIONS", "both models", "configuration boundary", "base three-axis; optional rotary excluded", "category", "base quote only", "NCX7 and NCX10 base",
        "Rotary, probing and through-spindle coolant not tested", "SYNTHETIC / TEST ONLY: both base configurations are three-axis; rotary, probing and through-spindle coolant are separately quoted options with untested applicability.")
    add("E3", "NCX10-SPEED", "NCX10", "continuous unloaded speed", 10000, "rpm", "NOVA-TEST-10; 20 C; unloaded bench", "NCX10 base",
        "Not a loaded-cutting or production guarantee", "SYNTHETIC / TEST ONLY: NCX10 spindle rated 10000 rpm continuously under NOVA-TEST-10 at 20 C on an unloaded bench; loaded cutting and production remain unassessed.")
    add("E3", "WARMUP", "both models", "trial warm-up", 30, "min", "before trial measurements; flood coolant; 20 C room", "documented trials only",
        "No thermal drift characterization", "SYNTHETIC / TEST ONLY: trial measurements follow 30 min warm-up with flood coolant in a 20 C room; this procedure is not thermal drift characterization.")
    add("E3", "NCX7-COUPON", "NCX7", "coupon measured dimensional deviation", "+/-0.02", "mm", "NOVA-MEASURE-A; aluminum; 20 C; fixture A", "coupon geometry only",
        "No other material, geometry or production guarantee", "SYNTHETIC / TEST ONLY: NCX7 aluminum coupon measured +/-0.02 mm at 20 C under NOVA-MEASURE-A with fixture A; other geometries and production remain unassessed.")
    add("E3", "NCX10-COUPON", "NCX10", "coupon measured dimensional deviation", "+/-0.02", "mm", "NOVA-MEASURE-A; aluminum; 20 C; fixture A", "same coupon geometry only",
        "Equal observed deviation does not establish equal production accuracy", "SYNTHETIC / TEST ONLY: NCX10 aluminum coupon measured +/-0.02 mm at 20 C under NOVA-MEASURE-A with fixture A; this result is not production accuracy assurance.")
    add("E3", "MEASUREMENT", "coupon trials", "measurement method and uncertainty", 0.005, "mm", "three coupons per machine; drawing A outer width; comparator; 20 C", "outer width only",
        "Not bore position, surface finish, process capability or calibration certification", "SYNTHETIC / TEST ONLY: NOVA-MEASURE-A checks outer width on three coupons per machine using a comparator with assumed uncertainty 0.005 mm; bore position and surface finish remain unassessed.")
    add("E4", "AL-PART", "aluminum trial", "material and blank", [120, 80, 30], "mm", "6061-T6; fixture A; pocket drawing A", "both models documented trial",
        "Not thin walls, deep cavities or hardened alloys", "SYNTHETIC / TEST ONLY: both aluminum trials use 6061-T6 blanks 120 mm by 80 mm by 30 mm and fixture A on pocket drawing A; thin walls and deep cavities remain unassessed.")
    add("E4", "AL-TOOL", "aluminum trial", "tool and coolant", 12, "mm", "three-flute carbide end mill; flood coolant", "both models same tool and fixture A",
        "Not dry cutting or other tool materials", "SYNTHETIC / TEST ONLY: aluminum trials use a 12 mm three-flute carbide end mill with flood coolant; dry cutting and other tool materials remain unassessed.")
    add("E4", "AL-CUT", "aluminum trial", "speed feed axial and radial engagement", [6000, 1800, 2, 6], "rpm; mm/min; mm; mm", "same programmed path; same tool; fixture A", "NCX7 and NCX10 aluminum trials",
        "Trial recipe only; not universal recommendation", "SYNTHETIC / TEST ONLY: aluminum trial recipe is 6000 rpm, 1800 mm/min feed, 2 mm axial depth and 6 mm radial width on both machines; it is not a universal cutting recommendation.")
    for model, seconds in (("NCX7", 42), ("NCX10", 40)):
        add("E4", model+"-AL-CYCLE", model, "aluminum programmed cycle observed", seconds, "s", "mean of three trial cycles; excludes loading; drawing A; same recipe", "fixture A aluminum trial only",
            "No statistical or general throughput advantage", f"SYNTHETIC / TEST ONLY: {model} aluminum trial mean cycle was {seconds} s across three runs on drawing A, excluding loading; the small sample establishes no general throughput advantage.")
    add("E4", "STEEL-CUT", "NCX10", "steel trial recipe", [1800, 240, 1, 4], "rpm; mm/min; mm; mm", "S45C unhardened blank; 10 mm four-flute carbide; flood coolant; fixture B", "NCX10 only",
        "No NCX7 steel comparison; not hardened steel", "SYNTHETIC / TEST ONLY: NCX10 trial uses unhardened S45C, a 10 mm four-flute carbide tool, 1800 rpm, 240 mm/min feed, 1 mm depth and 4 mm width with flood coolant and fixture B.")
    add("E4", "STEEL-RESULT", "NCX10", "steel feature observation", "+/-0.03", "mm", "NOVA-MEASURE-B; 20 C; fixture B; three coupons; drawing B outer width", "unhardened S45C coupon only",
        "No NCX7 comparison or production guarantee", "SYNTHETIC / TEST ONLY: NCX10 steel outer width measured +/-0.03 mm under NOVA-MEASURE-B at 20 C on three coupons with fixture B; NCX7 steel performance and production remain unassessed.")
    add("E4", "LIMITS", "application scope", "excluded applications", "titanium; hardened steel; unattended production", "category", "no trials supplied", "both machines",
        "Require new testing before claims", "SYNTHETIC / TEST ONLY: titanium, hardened steel and unattended production need new representative trials; the supplied records establish no suitability conclusion for these applications.")
    add("E5", "FIT-LARGE", "model shortlist", "larger fixture scenario", [800, 480, 520], "mm; mm; kg", "fixture footprint and combined centered static mass; machining path not assessed", "NCX7 versus NCX10 base",
        "NCX10 candidate only; travel, access, offsets and dynamic load require validation", "SYNTHETIC / TEST ONLY: an 800 mm by 480 mm fixture totaling 520 kg exceeds NCX7 table width and proposed load; NCX10 remains a candidate pending travel, access and dynamic-load checks.")
    add("E5", "FIT-SMALL", "model shortlist", "smaller fixture scenario", [400, 250, 180], "mm; mm; kg", "fixture footprint and combined centered static mass; path pending", "both machines base",
        "Nominal fit is not machining suitability", "SYNTHETIC / TEST ONLY: a 400 mm by 250 mm fixture totaling 180 kg is inside both nominal table and centered static-load proposals; path, tool reach and machining suitability still require review.")
    add("E5", "COMPARE-SPEED", "model shortlist", "spindle comparison limit", "unloaded ratings only", "category", "different unloaded bench protocols; no torque curves", "both machines",
        "Cannot rank steel removal or cycle time from rated speed", "SYNTHETIC / TEST ONLY: the different unloaded spindle ratings do not rank steel removal or cycle time; compare a representative loaded cycle and request torque records before choosing on speed.")
    add("E5", "COMPARE-TRIAL", "model shortlist", "equal-condition comparison scope", "aluminum drawing A only", "category", "same tool coolant fixture recipe; small sample", "both models aluminum",
        "No significance, durability or lifetime ranking", "SYNTHETIC / TEST ONLY: only aluminum drawing A has a matched trial on both models; its small sample does not establish significance, durability or lifetime cost rankings.")
    add("E5", "CONFIG-REVIEW", "buyer", "configuration confirmation", "base versus quoted options", "category", "before purchase order", "both machines",
        "Fixture A records do not validate options", "SYNTHETIC / TEST ONLY: confirm the quoted control, spindle, coolant, tool layout and options against the tested base configuration; fixture A records do not validate optional equipment.")
    add("E6", "RFQ", "buyer enquiry", "required RFQ inputs", "drawing revision; material; tolerances; fixture; tool list; cycle; utilities", "checklist", "before application review", "both machines",
        "Supplier must review actual inputs; no acceptance by submission alone", "SYNTHETIC / TEST ONLY: the proposed RFQ includes drawing revision, material, critical tolerances, fixture layout, tool list, target cycle and utilities; supplier review remains required.")
    add("E6", "FAT-CONDITIONS", "proposed FAT", "trial preparation", [30, 20], "min; C", "NOVA-ACCEPT-A; buyer drawing A; fixture A; same tool and coolant as trial", "aluminum proposed FAT for either machine",
        "Proposal only; buyer and supplier have not agreed", "SYNTHETIC / TEST ONLY: NOVA-ACCEPT-A proposes 30 min warm-up at 20 C using buyer drawing A, fixture A and the trial tool and coolant; buyer and supplier must agree this procedure.")
    add("E6", "FAT-CRITERION", "proposed FAT", "outer width acceptance threshold", "+/-0.025", "mm", "three consecutive coupons; comparator uncertainty assumed 0.005 mm; decision rule pending", "drawing A outer width only",
        "Negotiable proposal, not agreed tolerance or capability guarantee", "SYNTHETIC / TEST ONLY: proposed outer width criterion is +/-0.025 mm on three consecutive drawing A coupons with assumed uncertainty 0.005 mm; the measurement decision rule requires agreement.")
    add("E6", "FAT-CYCLE", "proposed FAT", "cycle threshold status", "to be negotiated", "status", "include loading and tool changes if production target demands them", "buyer actual production cycle",
        "Bench cycle timings are not contractual production limits", "SYNTHETIC / TEST ONLY: production cycle criteria remain to be negotiated with loading and tool changes defined explicitly; bench cycle timings are not contractual production limits.")
    add("E6", "FAT-ROLES", "proposed FAT", "responsibilities and disposition", "buyer approves drawing; supplier records setup; joint signoff; re-test after correction", "procedure", "before shipment release", "quoted machine serial and configuration",
        "No shipment release by automated test or this dossier", "SYNTHETIC / TEST ONLY: buyer approves the test drawing, supplier records setup and measurements, and both parties agree disposition and re-test after correction before shipment release.")
    add("E6", "SAT", "proposed SAT", "site checks", "utility readiness; configuration; repeat representative piece", "checklist", "after installation; site environmental conditions recorded", "delivered machine",
        "FAT does not substitute for agreed site acceptance", "SYNTHETIC / TEST ONLY: proposed site acceptance records utility readiness and installed configuration, then repeats an agreed representative piece; factory trials do not substitute for site agreement.")
    add("E7", "DELIVERY", "commercial proposal", "dispatch lead time", 60, "days", "after deposit and signed configuration; before international transit", "both base machines; fictional offer",
        "Options may change schedule; not arrival promise", "SYNTHETIC / TEST ONLY: base-machine dispatch is proposed within 60 days after deposit and signed configuration; options may change the schedule and international transit is excluded.")
    add("E7", "HANDOVER", "commercial proposal", "delivery exclusions", "freight; import duties; rigging; utilities", "category", "buyer-supplier contract pending", "fictional base offer",
        "Trade term and destination quotation pending", "SYNTHETIC / TEST ONLY: freight, import duties, rigging and site utilities are outside the base proposal; the trade term and destination quotation require agreement.")
    add("E7", "TRAINING", "commercial proposal", "training scope", 2, "days", "English remote sessions after utility readiness; designated operators", "base operation and maintenance",
        "Not advanced programming or on-site commissioning", "SYNTHETIC / TEST ONLY: training proposes 2 days of English remote sessions for designated operators on base operation and maintenance; advanced programming and on-site commissioning require separate agreement.")
    add("E7", "RESPONSE", "commercial proposal", "initial support response", 2, "business days", "email; declared support calendar; after ticket with diagnostics", "both base machines",
        "Initial response is not restoration time", "SYNTHETIC / TEST ONLY: initial email support response is proposed within 2 business days after a ticket with diagnostics under the declared support calendar; restoration time is not promised.")
    add("E7", "WARRANTY", "commercial proposal", "parts warranty duration", 12, "months", "from dispatch; manufacturing defects; diagnosis required", "both base machines",
        "Consumables misuse and travel excluded; final signed terms pending", "SYNTHETIC / TEST ONLY: proposed parts warranty is 12 months from dispatch for diagnosed manufacturing defects; consumables, misuse and travel are excluded and final signed terms are pending.")
    add("E7", "SPARES", "commercial proposal", "spares availability status", "quotation on request", "status", "part identifier and destination needed", "base machines",
        "No local stock or guaranteed shipping time", "SYNTHETIC / TEST ONLY: replacement parts require a part identifier and destination quotation; this proposal makes no local-stock or shipping-time commitment.")
    add("E7", "REGISTER", "dossier register", "revision and reuse", "B-TEST; retained E1; fixture A; fixture B steel only", "version", "valid only within this offline case; dated register", "all seven fictional records",
        "No certification, actual customer approval or engineering authentication", "SYNTHETIC / TEST ONLY: register B-TEST retains the original NCX7 spindle note and uses fixture A except NCX10 steel fixture B; these records provide no certification or actual customer approval.")
    return tuple(out)


BRIEF_INSTRUCTIONS = (
    "Audience: English-speaking import procurement managers and manufacturing engineers shortlisting a vertical machining center. Intent: commercial investigation before an RFQ, not a universal ranking. Help them specify a part and compare conditional fit. All customer material is SYNTHETIC / TEST ONLY, never engineering certification or real signoff.",
    "Machine and application fit: what part-plus-fixture envelope, combined load and tool layout are required? Use E2 travels, tables, loads and BT40 constraints; compare E5 small and large fixture scenarios. Explain why nominal dimensions are screening criteria rather than validated usable envelope. Next action: send fixture layout, path and tool-reach questions. Retain distinct NCX7 and NCX10 facts; do not combine their capacities.",
    "Spindle and cutting evidence: what do continuous unloaded ratings establish, and what remains unknown under load? Use E1 and E3 protocols, motor-nameplate definition, warm-up and coupon observations; E4 material, tooling, coolant, feed, engagement and cycle records. Compare only the matched aluminum trial; explain its sample and loading exclusions. Do not rank steel removal from unloaded speed or infer torque curves, thermal stability or general accuracy.",
    "Application limits and model comparison: which scenario has supporting trials? E4 supports only aluminum drawing A on both machines and unhardened S45C fixture B on NCX10. E5 makes conditional shortlist judgments, not recommendations. Distinguish observed coupon deviation from nominal capacity and contractual tolerance. Titanium, hardened steel, unattended production, optional rotary and other geometries remain unanswered pending representative tests.",
    "Procurement and acceptance: what should the buyer send, what should both parties measure and agree, and who owns disposition? E6 RFQ list, proposed warm-up, coupon criterion, measurement uncertainty, undecided decision rule, production-cycle boundary, responsibilities and site repeat. Present these as negotiable proposals, never customer-approved acceptance or guarantees. Next action: request the exact test setup and agree drawing, loading, measurement rule, serial/configuration and re-test criteria.",
    "Delivery training and support: distinguish dispatch after deposit/configuration from arrival; initial response from restoration; base remote training from separately agreed commissioning. Use E7 only within its fictional offer, exclusions and unsigned status. Ask for destination, site utility, support calendar, parts and signed contract details. No certification, customer testimonial, global service network or local-stock claims.",
    "For every substantive explanation follow product fact -> meaning to buyer -> how to judge applicability -> next action. Map claims to E and retain source revision, test conditions and exclusions. Keep S as attributed general purchasing context, never disguise E as P/S. Avoid copied S sentences and parameter dumps. Use natural transitions and a CTA asking for drawing, fixture, tool list and an agreed test proposal; promise no results. No minimum word count.",
    "Mandatory unknowns: torque curves, statistical capability, long-run thermal drift, tool life, surface finish, bore positioning, safety/regulatory compliance, final price, landed cost, local support coverage and actual shipment are not established. Ask for applicable records or omit conclusions. Native Plan, reference, quotation and budget constraints prevail; if they prevent these sections or supporting facts, mark the experiment BLOCKED instead of replacing the Plan or inventing prose.",
)
