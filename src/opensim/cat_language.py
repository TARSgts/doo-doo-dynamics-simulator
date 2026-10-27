import re


PHRASES = {
    "Uniform surface traction": "Spread da boops", "Traction surface": "Boop dis surface",
    "Distributed load": "Boops everywhere", "Uniform traction study": "Evenly spread boop science",
    "Doo Doo Dynamics Simulator — Structural Workbench": "Doo Doo Dynamics Simulator — Catputer Lab",
    "DOO DOO DYNAMICS  /  SIMULATOR": "DOO DOO DYNAMICS  /  MEOWMULATOR",
    "File": "Box of stuff", "Help": "Halp", "View": "Lookies", "About": "Who dis?", "Exit": "I go nap",
    "Home": "Cat bed", "Geometry": "Shapez", "Mesh": "Tiny triangles", "Environment": "Surroundings",
    "Solution": "Science", "Automation": "Robot paws", "Validation": "Did it work tho?",
    "New project": "New cardboard box", "Workspace": "Cardboard kingdom", "Import CAD": "Bring da shape",
    "Create test plate": "Spawn snack plate", "Test plate": "Snack plate", "Built-in example": "One we made earlier, nya",
    "Generate mesh": "Make tiny triangles", "Gmsh tetrahedra": "Gmsh triangle beans", "Linear tetrahedra": "Pointy beans",
    "Solve": "Do a science, meow", "Static structural": "Sit still science", "Static Structural": "Sit still science",
    "Results": "Look what I did", "Displacement": "Wiggles", "Current result": "Latest science loot",
    "Modal analysis": "Find da wiggles", "Modal": "Wiggles", "Natural frequencies": "Purr frequencies",
    "Cantilever": "Long boi", "Create beam preset": "Spawn long boi", "Reference report": "Proof I did science",
    "Euler–Bernoulli study": "Euler–Bernoulli long boi", "Bending + shear study": "Bendy + squishy science",
    "Circular hole": "Forbidden donut", "Kirsch stress study": "Kirsch donut stress", "Frequency verification": "Check da purrs",
    "Thermal analysis": "Warm loaf science", "Thermal": "Warm loaf", "Fluid dynamics": "Water bowl chaos",
    "Transient dynamics": "Zoomies over time", "Electromagnetics": "Invisible zappy stuff", "Contact": "Boop detection",
    "Nonlinear materials": "Extra squishy stuff", "Optimization": "Make it more purrfect", "GPU solve": "Fancy zoomies solve",
    "CAD editing": "Shape grooming", "Assemblies": "Pile of stuff", "Adaptive refinement": "More triangle beans",
    "Apply settings": "Use dese settings", "Material / axial force": "Stuff / big push", "Face selection": "Pick a face, nya",
    "Stress contours": "Where it feels spicy", "Planned": "Still snoozin", "Remote access": "Long-distance paws",
    "MCP status": "Robot paw status", "MCP Controls": "Robot paw controls", "Refresh": "Look again",
    "Shared workspace": "Shared cardboard box", "Outline / Model": "Stuff in da box", "Analysis Toolbox": "Science toybox",
    "Messages / Solver Jobs": "Science gossip", "AVAILABLE NOW": "CAN HAZ NOW", "PLANNED FEATURES": "STILL NAPPING",
    "DETAILS OF STATIC STRUCTURAL": "DETAILS OF SIT STILL SCIENCE", "DETAILS OF MODAL ANALYSIS": "DETAILS OF DA WIGGLES",
    "Mesh size": "Triangle smolness", "CAD scale to m": "Shape size to m", "Young's E": "Stiffness of da boi",
    "Poisson ratio": "Sideways squish", "Density": "Chonk density", "Total force": "Big push",
    "Requested modes": "How many wiggles", "Elements": "Triangle beans", "Force direction": "Push dis way",
    "Force application": "Where to boop", "Fixed support": "Stay right here", "Static force": "Sit still push",
    "Tip center": "Tip boop", "End face": "End boop", "Quadratic": "Extra curvy", "Linear": "Straight-ish",
    "Fit view": "Fits in box", "Edges": "Pointy bits", "Deformation": "Wiggle size", "True scale": "Actual smolness",
    "Iso": "Cat angle", "Front XZ": "Front XZ, nya", "Top XY": "Top XY, nya", "Mode": "Wiggle",
    "Animate mode": "Make it dance", "Pause mode": "Stop da dance", "Back to model": "Back to da shape",
    "Maximum displacement": "Biggest wiggle", "Maximum |U|": "Biggest |U|", "Tip-section displacement": "Tip boop wiggle",
    "Tip mean": "Tip boop mean", "Force balance residual": "Push balance leftovers", "Force balance": "Push balance",
    "Extracted modes": "Wiggles found", "Mode shape": "Wiggle shape", "Normalized": "Same-size wiggle",
    "arbitrary amplitude": "pretend wiggle size", "animation plays at": "dance speed is", "dimensionless": "dimensionless, nya",
    "Ready": "Ready, meow", "Light mode": "Sunbeam mode", "Dark mode": "Night prowl mode",
    "No jobs yet.": "No science yet, human.", "No solved result for current settings": "No science loot for dese settings yet",
}

PATTERN = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(phrase) for phrase in sorted(PHRASES, key=len, reverse=True)) + r")(?!\w)", re.IGNORECASE)
LOOKUP = {phrase.casefold(): translated for phrase, translated in PHRASES.items()}


def cat_text(text):
    def replace(match):
        translated = LOOKUP[match.group().casefold()]
        return translated.upper() if match.group().isupper() else translated
    return PATTERN.sub(replace, text)
