"""
Funny Valentine -> Deadlock hero model swap, the lazy way.

Takes any rigged humanoid (made for the Sketchfab "FUNNY VALENTINE & D4C" model,
but anything Mixamo / Rigify / MMD / VRM-ish works) and fits it onto a Deadlock
hero's skeleton so the hero's own animations drive it:

  1. imports the hero skeleton + body from the Source 2 Viewer decompile (needs
     Blender Source Tools, same as any other Deadlock model mod)
  2. imports Funny Valentine, turns him to face +X, scales him to the hero's height
  3. warps his mesh so every joint (shoulders, elbows, wrists, knees...) lands
     exactly on the hero's joints and his arms/legs match the hero's bind pose
  4. renames his skin weights onto the hero's bones
  5. keeps the hero's gun (and any door props) so reload/shoot anims still work
  6. writes funny_valentine.dmx, the .vmat/.png materials, and patches the hero
     .vmdl so it uses FV instead of the original body + head

Nothing about the skeleton is touched, so the stock animgraph keeps working.

Run (Blender 4.1+ with Blender Source Tools enabled):

  blender -b -P fv_build.py -- --model source/scene.gltf --hero-dir "C:/CSDK12/content/citadel_addons/funny_valentine/models/heroes_wip/doorman_v2"

or open it in Blender's Scripting tab, fill in CONFIG below and hit Run (it clears the scene).
`--help` lists every option.
"""

import argparse
import math
import os
import re
import shutil
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

# Used when the script is run from Blender's text editor (no command line args).
CONFIG = {
    "model": "",       # path to the Funny Valentine .gltf/.glb/.fbx/.blend/.dmx
    "hero_dir": "",    # S2V decompile folder that holds e.g. doorman.vmdl + doorman_doorman.dmx
}

OUT_NAME = "funny_valentine"
MAT_DIR = "materials/funny_valentine"

# Stuff on the FV side we never want on the hero.
DEFAULT_EXCLUDE = "d4c,dirty,deeds,outline,icosphere,eyelash"   # eyelash cards need alpha test, just drop them
# Hero body faces with these materials are kept (Doorman's gun + portable doors).
DEFAULT_KEEP_MATS = "gun,weapon,door"
# Extra hero render meshes to drop from the .vmdl (the body mesh is always replaced).
DEFAULT_DROP_MESHES = "head"

SIDES = ("L", "R")


def log(*a):
    print("[fv]", *a, flush=True)


def die(msg):
    print("\n[fv] ERROR: " + msg + "\n", flush=True)
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# args


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(prog="fv_build.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--model", default=CONFIG["model"], help="Funny Valentine model file")
    p.add_argument("--hero-dir", default=CONFIG["hero_dir"],
                   help="folder with the decompiled hero .vmdl + .dmx files, inside your CSDK addon's content folder")
    p.add_argument("--vmdl", default="", help="hero .vmdl to patch (default: the only/biggest one in --hero-dir)")
    p.add_argument("--body", default="", help="render mesh name to replace (default: the one named like the hero)")
    p.add_argument("--drop", default=DEFAULT_DROP_MESHES,
                   help="comma list: other hero render meshes to remove (substring match), default 'head'")
    p.add_argument("--keep-mats", default=DEFAULT_KEEP_MATS,
                   help="comma list: hero body materials to keep on the new model, default 'gun,weapon,door'")
    p.add_argument("--exclude", default=DEFAULT_EXCLUDE,
                   help="comma list: FV-side meshes to throw away (substring match on object/material name)")
    p.add_argument("--textures", default="", help="folder to look in for textures the model can't find")
    p.add_argument("--gun", default="", help="replace the hero's gun with this model (e.g. an old revolver)")
    p.add_argument("--gun-grip", default="1.1,0,1.0",
                   help="where the palm holds the gun, in the gun's bind space (Doorman: 1.1,0,1.0 - measured)")
    p.add_argument("--gun-scale", type=float, default=1.0, help="extra size multiplier for --gun")
    p.add_argument("--gun-forward", default="", help="axis the --gun barrel points along in its file, e.g. -y (guessed if unset)")
    p.add_argument("--gun-up", default="", help="axis pointing out of the top of the --gun in its file, e.g. +z (guessed if unset)")
    p.add_argument("--pick", default="", help="substring of the armature to use if the file has several (FV vs D4C)")
    p.add_argument("--scale", type=float, default=1.0, help="extra size multiplier after matching the hero's height")
    p.add_argument("--weights", choices=("auto", "model", "hero"), default="auto",
                   help="'model' = keep FV's own skinning, 'hero' = copy the hero's skin weights by proximity")
    p.add_argument("--with-stand", action="store_true",
                   help="also bring D4C along, floating behind him (rigid, not animated)")
    p.add_argument("--bone-map", default="",
                   help="JSON file {\"fv bone\": \"hero bone\"} to override the automatic bone matching")
    p.add_argument("--save-blend", default="", help="save the fitted scene to this .blend so you can tweak it")
    p.add_argument("--preview", default="", help="render front/side preview PNGs to this path prefix")
    a = p.parse_args(argv)
    if not a.model or not a.hero_dir:
        p.print_help()
        die("need --model and --hero-dir (or fill in CONFIG at the top of the script)")
    a.model = os.path.abspath(bpy.path.abspath(a.model))
    a.hero_dir = os.path.abspath(bpy.path.abspath(a.hero_dir))
    return a


def csv(s):
    return [x.strip().lower() for x in s.split(",") if x.strip()]


def mat_has(mat, words):
    """Whole-word match on a material's file name: 'gun' hits doorman_gun.vmat, 'door' doesn't hit doorman_body."""
    if not mat:
        return False
    stem = os.path.splitext(os.path.basename(mat.name.lower()))[0]
    return bool(set(re.split(r"[^0-9a-z]+", stem)) & set(words))


# ---------------------------------------------------------------------------
# Blender Source Tools


def ensure_bst():
    import addon_utils
    if not hasattr(bpy.ops.import_scene, "smd") or not hasattr(bpy.types.Scene, "vs"):
        for mod in addon_utils.modules():
            if "valvesource" in mod.__name__ or "source_tools" in mod.__name__:
                addon_utils.enable(mod.__name__, default_set=True)
                break
    if not hasattr(bpy.types.Scene, "vs"):
        die("Blender Source Tools isn't installed/enabled. Get it from "
            "https://github.com/Artfunkel/BlenderSourceTools/releases (Edit > Preferences > Add-ons > Install).")


def dmx_material_paths(path):
    """{'doorman_gun.vmat': 'models/.../doorman_gun.vmat'} straight from the DMX, via BST's datamodel module."""
    import importlib
    import addon_utils
    for mod in addon_utils.modules():
        if "valvesource" in mod.__name__ or "source_tools" in mod.__name__:
            try:
                dm = importlib.import_module(mod.__name__ + ".datamodel").load(path)
            except Exception as ex:
                log("couldn't read material paths from the dmx:", ex)
                return {}
            out = {}
            for e in dm.elements:
                if e.type == "DmeMaterial" and e.get("mtlName"):
                    name = e["mtlName"].replace("\\", "/")
                    base = os.path.basename(name)
                    out[base.lower()] = name
                    out[os.path.splitext(base)[0].lower()] = name
            return out
    return {}


# ---------------------------------------------------------------------------
# small scene helpers


def new_objects(before):
    return [o for o in bpy.data.objects if o.name not in before]


def delete(objs):
    for o in list(objs):
        if o and o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)


def link_to_scene(o):
    if not o.users_collection:
        bpy.context.scene.collection.objects.link(o)


def bake_world_transform(o):
    """Clear parent keeping the world transform, then bake it into the data."""
    mw = o.matrix_world.copy()
    o.parent = None
    o.matrix_world = mw
    if o.type == "MESH":
        o.data.transform(mw)
        o.matrix_world = Matrix()
    elif o.type == "ARMATURE":
        o.data.transform(mw)
        o.matrix_world = Matrix()


def strip_shape_keys(o):
    if o.data.shape_keys:
        o.shape_key_clear()


def world_bbox(objs):
    pts = []
    for o in objs:
        if o.type == "MESH" and len(o.data.vertices):
            co = np.empty(len(o.data.vertices) * 3)
            o.data.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            mw = np.array(o.matrix_world)
            co = co @ mw[:3, :3].T + mw[:3, 3]
            pts.append(co.min(0))
            pts.append(co.max(0))
    if not pts:
        return Vector((0, 0, 0)), Vector((0, 0, 0))
    pts = np.array(pts)
    return Vector(pts.min(0)), Vector(pts.max(0))


# ---------------------------------------------------------------------------
# bone name understanding

PREFIX_TOKENS = re.compile(
    r"^(mixamorig\d*|mixamo|bip\d*|valvebiped|def|org|mch|j|b|bone|cc|base|armature|rig|character|"
    r"skeleton|jnt|joint|jt|sk|gltf|created|node|valve)$")
NOISE_TOKENS = {"end", "nub", "tip", "twist", "roll", "ik", "pole", "target", "ctrl", "control", "helper",
                "dummy", "null", "offset", "jiggle", "root", "top", "notwist", "meta", "ref", "attach",
                "socket", "weapon", "prop", "scale", "scapula", "aim", "lookat"}
FINGERS = {"thumb": "thumb", "index": "index", "middle": "middle", "ring": "ring", "pinky": "pinky",
           "pinkie": "pinky", "little": "pinky", "small": "pinky"}
JP_FINGERS = {"親指": "thumb", "人指": "index", "人差指": "index", "中指": "middle", "薬指": "ring", "小指": "pinky"}


def tokenize(name):
    name = re.sub(r"_\d+$", "", name)            # Sketchfab glTF appends _NN to every node
    name = re.sub(r"\.\d{3}$", "", name)          # Blender duplicate suffix
    parts = re.split(r"[^0-9A-Za-z\u3040-\u30ff\u4e00-\u9fff\uff10-\uff5a]+", name)
    toks = []
    for p in parts:
        toks += re.findall(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+|[^\x00-\x7f]+", p)
    return [t for t in toks if t]


def classify(name):
    """Return (class, side) for a bone name, class None if it's not a main body bone."""
    raw = re.sub(r"_\d+$", "", name)
    side = None
    if "左" in raw:
        side = "L"
    elif "右" in raw:
        side = "R"
    toks = tokenize(name)
    base_toks = []
    for t in toks:
        tl = t.lower()
        if tl in ("l", "left", "lft", "lf"):
            side = side or "L"
            continue
        if tl in ("r", "right", "rgt", "rt"):
            side = side or "R"
            continue
        if PREFIX_TOKENS.match(tl):
            continue
        base_toks.append(tl)
    jp = raw.replace("左", "").replace("右", "")
    base = "".join(t for t in base_toks if not t.isdigit())
    tokset = set(base_toks)

    # --- MMD Japanese
    if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", jp):
        if re.search("捩|ＩＫ|IK|先EX|親$|センター|グルーブ|操作|ダミー|全ての親", jp):
            return None, side
        for k, v in JP_FINGERS.items():
            if k in jp:
                return "f_" + v, side
        for k, c in (("手首", "hand"), ("足首", "foot"), ("つま先", "toe"), ("ひじ", "forearm"), ("肘", "forearm"),
                     ("ひざ", "shin"), ("膝", "shin"), ("下半身", "hips"), ("上半身", "spine"), ("首", "neck"),
                     ("頭", "head"), ("肩", "shoulder"), ("腕", "upperarm"), ("足", "thigh")):
            if k in jp:
                return c, side
        return None, side

    if not base or tokset & NOISE_TOKENS:
        return None, side
    if base.endswith("d") and base[:-1] in ("leg", "knee", "ankle", "toe"):   # MMD "D" deform bones
        base = base[:-1]
    # face/hair/cloth bones follow their parent; match whole tokens ("forearm" contains "ear"),
    # and before fingers: "Head_Lip_Lower_Middle" is not a middle finger
    if any(t.startswith(k) for t in base_toks for k in ("eye", "brow", "lid", "lash", "mouth", "lip", "tongue",
                                                          "teeth", "cheek", "nose", "ear", "hair", "cloth", "coat",
                                                          "skirt", "cape", "tail", "breast", "bust")):
        return None, side
    for k, v in FINGERS.items():
        if any(t.startswith(k) for t in base_toks):
            return "f_" + v, side
    if "hand" in base or "wrist" in base or "palm" in base:
        return "hand", side
    if "forearm" in base or "lowerarm" in base or "armlower" in base or "elbow" in base or base == "lowarm":
        return "forearm", side
    if base in ("arm", "upperarm", "uparm", "armupper", "bicep") or base.endswith("upperarm"):
        return "upperarm", side
    if "clavicle" in base or "shoulder" in base or "collar" in base:
        return "shoulder", side
    if "toe" in base or base in ("ball", "football"):
        return "toe", side
    if "foot" in base or "ankle" in base:
        return "foot", side
    if any(k in base for k in ("shin", "calf", "knee", "lowerleg", "leglower", "crus")):
        return "shin", side
    if any(k in base for k in ("thigh", "upleg", "upperleg", "legupper")):
        return "thigh", side
    if base == "leg":
        return "leg?", side
    if "neck" in base:
        return "neck", side
    if base == "head" or base.startswith("head"):
        return "head", side
    if "jaw" in base or "chin" in base:
        return "jaw", side
    if base in ("hips", "hip", "pelvis", "lowerbody", "waist", "cog"):
        return "hips", side
    if any(k in base for k in ("spine", "chest", "upperbody", "torso", "abdomen", "belly")):
        return "spine", side
    return None, side


def depth(bone):
    d = 0
    while bone.parent:
        bone = bone.parent
        d += 1
    return d


class Rig:
    """Semantic view of an armature: rig.get('hand', 'L') -> bone name."""

    LIMB_PARENTS = (("hand", "forearm"), ("forearm", "upperarm"), ("shin", "thigh"))

    def __init__(self, arm_obj, overrides=None):
        self.obj = arm_obj
        self.bones = arm_obj.data.bones
        self.cls = {}          # bone name -> (class, side)
        self.slots = {}        # (class, side) -> primary bone name
        self.spine = []        # ordered torso chain (excluding hips/neck/head)
        self.fingers = {}      # (finger, side) -> [bone names root->tip]
        self.overrides = dict(overrides or {})
        for b in self.bones:
            self.cls[b.name] = classify(b.name)
        for fv_name, hero_name in self.overrides.items():
            if fv_name not in self.bones:
                log("!! --bone-map: no bone called %r in the model" % fv_name)
            self.cls[fv_name] = hero_class(hero_name)
        self._resolve_legs()
        self._pick_slots()
        self._fill_gaps()

    def _resolve_legs(self):
        for s in SIDES + (None,):
            legs = [n for n, c in self.cls.items() if c == ("leg?", s)]
            if not legs:
                continue
            has_thigh = any(c == ("thigh", s) for c in self.cls.values())
            has_shin = any(c == ("shin", s) for c in self.cls.values())
            for n in legs:
                if has_thigh and not has_shin:
                    self.cls[n] = ("shin", s)
                elif has_shin and not has_thigh:
                    self.cls[n] = ("thigh", s)
                else:
                    par = self.bones[n].parent
                    pc = self.cls.get(par.name, (None, None))[0] if par else None
                    self.cls[n] = ("shin" if pc in ("thigh", "leg?") else "thigh", s)

    def _pick_slots(self):
        by_slot = {}
        for n, (c, s) in self.cls.items():
            if c:
                by_slot.setdefault((c, s), []).append(n)
        for key, names in by_slot.items():
            c, s = key
            names.sort(key=lambda n: depth(self.bones[n]))
            if c == "spine":
                continue
            if c.startswith("f_"):
                self.fingers[(c[2:], s)] = names[:3]
                continue
            self.slots[key] = names[0]
        spine = sorted([n for n, (c, s) in self.cls.items() if c == "spine"], key=lambda n: depth(self.bones[n]))
        self.spine = spine
        if ("hips", None) not in self.slots:
            for key in list(self.slots):
                if key[0] == "hips":
                    self.slots[("hips", None)] = self.slots[key]

    def _fill_gaps(self):
        def up(name):
            b = self.bones[name].parent
            while b is not None and self.cls.get(b.name, (None,))[0] is None and "twist" in b.name.lower():
                b = b.parent
            return b.name if b else None

        for s in SIDES:
            for child, parent in self.LIMB_PARENTS:
                if (child, s) in self.slots and (parent, s) not in self.slots:
                    p = up(self.slots[(child, s)])
                    if p:
                        self.slots[(parent, s)] = p
                        self.cls[p] = (parent, s)
        # Rigify calls the neck/head spine.004-.006: no head found -> top of the spine chain is the head
        if ("head", None) not in self.slots and len(self.spine) >= 3:
            self.slots[("head", None)] = self.spine.pop()
            self.cls[self.slots[("head", None)]] = ("head", None)
            if ("neck", None) not in self.slots and len(self.spine) >= 3:
                self.slots[("neck", None)] = self.spine.pop()
                self.cls[self.slots[("neck", None)]] = ("neck", None)
        if ("hips", None) not in self.slots:
            thighs = [self.slots.get(("thigh", s)) for s in SIDES]
            if all(thighs):
                p = self.bones[thighs[0]].parent
                if p:
                    self.slots[("hips", None)] = p.name
                    self.cls[p.name] = ("hips", None)
            elif self.spine:
                p = self.bones[self.spine[0]].parent
                if p:
                    self.slots[("hips", None)] = p.name
                    self.cls[p.name] = ("hips", None)

    def get(self, c, s=None):
        return self.slots.get((c, s))

    def has_limbs(self):
        return all(self.get(c, s) for c in ("upperarm", "forearm", "hand", "thigh", "shin") for s in SIDES)

    def head_pos(self, name):
        return self.obj.matrix_world @ self.bones[name].head_local

    def report(self):
        rows = []
        for key in sorted(self.slots, key=lambda k: (k[0], str(k[1]))):
            rows.append("%s%s=%s" % (key[0], "." + key[1] if key[1] else "", self.slots[key]))
        rows.append("spine=%s" % self.spine)
        rows.append("fingers=%s" % {"%s.%s" % k: v for k, v in self.fingers.items()})
        return "\n      ".join(rows)


def hero_class(hero_name):
    """Deadlock bone name -> (class, side), used to read --bone-map files."""
    m = re.fullmatch(r"(.+?)_([LR])", hero_name)
    base, side = (m.group(1), m.group(2)) if m else (hero_name, None)
    table = {"pelvis": "hips", "neck_0": "neck", "head": "head", "jaw_0": "jaw", "clavicle": "shoulder",
             "arm_upper": "upperarm", "arm_lower": "forearm", "hand": "hand", "leg_upper": "thigh",
             "leg_lower": "shin", "ankle": "foot", "ball": "toe"}
    if base in table:
        return table[base], side
    if re.fullmatch(r"spine_\d+", base):
        return "spine", None
    f = re.fullmatch(r"finger_(thumb|index|middle|ring|pinky)_\d", base)
    if f:
        return "f_" + f.group(1), side
    return None, side


# Deadlock heroes all share Valve's naming, so the hero side is a fixed table.
def hero_bone_for(fv_class, side, index, hero_bones, hero_spine):
    s = side
    table = {
        "hips": "pelvis", "neck": "neck_0", "head": "head", "jaw": "jaw_0",
        "shoulder": "clavicle_%s" % s, "upperarm": "arm_upper_%s" % s, "forearm": "arm_lower_%s" % s,
        "hand": "hand_%s" % s, "thigh": "leg_upper_%s" % s, "shin": "leg_lower_%s" % s,
        "foot": "ankle_%s" % s, "toe": "ball_%s" % s,
    }
    if fv_class == "spine":
        return hero_spine[index] if hero_spine else None
    if fv_class.startswith("f_"):
        name = "finger_%s_%d_%s" % (fv_class[2:], index, s)
    else:
        name = table.get(fv_class)
    return name if name and name in hero_bones else None


# ---------------------------------------------------------------------------
# vmdl (KV3 text) editing - just enough to swap render meshes


def block_spans(text):
    """Map of '{' index -> matching '}' index, ignoring braces inside strings."""
    spans, stack, i, n = {}, [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            if text.startswith('"""', i):
                i = text.index('"""', i + 3) + 3
                continue
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
        elif ch == "/" and text.startswith("//", i):
            i = text.find("\n", i)
            if i < 0:
                break
        elif ch == "{":
            stack.append(i)
        elif ch == "}":
            spans[stack.pop()] = i
        i += 1
    return spans


def enclosing_block(text, spans, idx):
    best = None
    for s, e in spans.items():
        if s < idx < e and (best is None or s > best[0]):
            best = (s, e)
    return best


def render_mesh_entries(text):
    spans = block_spans(text)
    out = []
    for m in re.finditer(r'_class\s*=\s*"RenderMeshFile"', text):
        s, e = enclosing_block(text, spans, m.start())
        body = text[s:e]
        name = re.search(r'\bname\s*=\s*"([^"]*)"', body)
        fn = re.search(r'\bfilename\s*=\s*"([^"]*)"', body)
        out.append({"start": s, "end": e, "name": name.group(1) if name else "",
                    "filename": fn.group(1) if fn else ""})
    return out


def remove_block(text, s, e):
    ls = text.rfind("\n", 0, s) + 1
    le = text.find("\n", e)
    le = len(text) if le < 0 else le + 1
    return text[:ls] + text[le:]


# ---------------------------------------------------------------------------
# materials


VMAT_TEMPLATE = """// Funny Valentine - generated by fv_build.py
// Deadlock's pbr.vfx only reads the layer-1 inputs (TextureColor1, TextureNormal1, ...);
// un-suffixed names like "TextureColor" are silently ignored. Layout matches Valve's hero materials.
"Layer0"
{{
	"shader"	"pbr.vfx"
	"F_RENDER_BACKFACES"	"{backfaces}"
	"F_SOLID_COLOR_OUTLINE"	"1"
	"F_USE_NPR_LIGHTING"	"1"
	"F_USE_STATUS_EFFECTS_PROXY"	"1"
	"g_bMaskColorTint1"	"1"
	"g_bMaskVertexColorTint1"	"1"
	"g_flAlbedoScrollQuantize1"	"0"
	"g_flHighlightAOStrength1"	"1"
	"g_flHighlightCoverage1"	"0"
	"g_flHighlightHardness1"	"0"
	"g_flHighlightNormalStrength1"	"64"
	"g_flHighlightRadius1"	"256"
	"g_flHighlightTintBrightness1"	"1"
	"g_flInvertHighlight1"	"0"
	"g_flNormalAndRoughnessScrollQuantize1"	"0"
	"g_fSolidOutlineVertexColorTint"	"0"
	"g_fVertexColorStrength1"	"1"
	"g_vAlbedoContrastSaturationBrightness1"	"[1.000000 1.000000 1.000000 0.000000]"
	"g_vAlbedoScrollSpeed1"	"[0.000000 0.000000 0.000000 0.000000]"
	"g_vColorTint1"	"[1.000000 1.000000 1.000000 0.000000]"
	"g_vHighlightPositionWs1"	"[0.000000 0.000000 72.000000 0.000000]"
	"g_vHighlightTint1"	"[1.000000 1.000000 1.000000 0.000000]"
	"g_vNormalAndRoughnessScrollSpeed1"	"[0.000000 0.000000 0.000000 0.000000]"
	"g_vSolidOutlineAdditive"	"[0.011765 0.011765 0.011765 0.000000]"
	"g_vSolidOutlineTint"	"[0.101961 0.101961 0.101961 0.000000]"
	"TextureColor1"	"{color}"
	"TextureAmbientOcclusion1"	"[1.000000 1.000000 1.000000 0.000000]"
	"TextureMetalness1"	"[0.000000 0.000000 0.000000 0.000000]"
	"TextureNormal1"	"[0.501961 0.501961 1.000000 0.000000]"
	"TextureRoughness1"	"[0.400000 0.400000 0.400000 0.000000]"
	"TextureSelfIllumMask1"	"[0.000000 0.000000 0.000000 0.000000]"
	"TextureNprOutlineMask1"	"[1.000000 1.000000 1.000000 0.000000]"
	"TextureNprTramsissiveColor1"	"[0.000000 0.000000 0.000000 0.000000]"
	"TextureRimLightMask1"	"[1.000000 1.000000 1.000000 0.000000]"
	"TextureTintMask1"	"[1.000000 1.000000 1.000000 0.000000]"
}}
"""



def write_png(path, w, h, rgba_flat):
    img = bpy.data.images.new("fv_tmp", w, h, alpha=True)
    img.pixels.foreach_set(np.asarray(rgba_flat, dtype=np.float32).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def save_image(img, path):
    try:
        if img.packed_file or not os.path.isfile(bpy.path.abspath(img.filepath)):
            img.filepath_raw = path
            img.file_format = "PNG"
            img.save()
            return True
        src = bpy.path.abspath(img.filepath)
        if src.lower().endswith(".png"):
            shutil.copyfile(src, path)
        else:
            img2 = img.copy()
            img2.filepath_raw = path
            img2.file_format = "PNG"
            img2.save()
            bpy.data.images.remove(img2)
        return True
    except Exception as ex:  # corrupt/unsupported image, fall back to a flat colour
        log("  couldn't save image", img.name, ex)
        return False


def relink_textures(model_path, extra_dir=""):
    """Point images whose file is missing at a same-named file near the model (textures/, ../textures/ ...)."""
    here = os.path.dirname(os.path.abspath(model_path))
    roots = [d for d in (extra_dir, here, os.path.dirname(here)) if d and os.path.isdir(d)]
    index = {}
    for r in roots:
        for dirpath, dirs, files in os.walk(r):
            if dirpath[len(r):].count(os.sep) >= 3:
                dirs[:] = []
            for f in files:
                if f.lower().endswith((".png", ".tga", ".jpg", ".jpeg", ".dds", ".bmp", ".tif", ".tiff", ".webp")):
                    key = re.sub(r"[ _]+", "_", f.lower())
                    index.setdefault(key, os.path.join(dirpath, f))
    fixed, missing = 0, []
    for img in bpy.data.images:
        if img.packed_file or img.source != "FILE" or not img.filepath:
            continue
        if os.path.isfile(bpy.path.abspath(img.filepath, library=img.library)):
            continue
        base = os.path.basename(img.filepath.replace("\\", "/"))
        hit = index.get(re.sub(r"[ _]+", "_", base.lower()))
        if hit:
            img["fv_orig_path"] = img.filepath
            img.filepath = hit
            img.reload()
            fixed += 1
        else:
            missing.append(base)
    if fixed or missing:
        log("textures: relinked %d%s" % (fixed, (", can't find %s" % missing) if missing else ""))


def base_color_source(mat):
    """(image or None, rgba) feeding the material's base colour."""
    rgba = (0.8, 0.8, 0.8, 1.0)
    if not mat or not mat.node_tree:
        if mat:
            rgba = tuple(mat.diffuse_color)
        return None, rgba
    nodes = mat.node_tree.nodes
    bsdf = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        bsdf = next((n for n in nodes if n.type in ("BSDF_DIFFUSE", "EMISSION")), None)
    start = None
    if bsdf:
        sock = bsdf.inputs.get("Base Color") or bsdf.inputs.get("Color")
        if sock is not None:
            rgba = tuple(sock.default_value)
            start = sock
    seen = set()

    def walk(sock):
        for link in sock.links:
            n = link.from_node
            if n.name in seen:
                continue
            seen.add(n.name)
            if n.type == "TEX_IMAGE" and n.image:
                return n.image
            for s in n.inputs:
                r = walk(s)
                if r:
                    return r
        return None

    img = walk(start) if start is not None else None
    if img is None:
        img = next((n.image for n in nodes if n.type == "TEX_IMAGE" and n.image), None)
    return img, rgba


def check_uvs(obj):
    """Stop if any textured material ended up with collapsed UVs (the whole part would be one texel)."""
    me = obj.data
    if len(me.uv_layers) != 1:
        die("expected one UV map after joining, got %s" % [l.name for l in me.uv_layers])
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers[0].data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    mat_of_loop = np.empty(len(me.loops), dtype=np.int32)
    for p in me.polygons:
        mat_of_loop[p.loop_start:p.loop_start + p.loop_total] = p.material_index
    for i, m in enumerate(me.materials):
        sel = uv[mat_of_loop == i]
        if len(sel) > 8 and len(np.unique(sel.round(4), axis=0)) <= 1:
            die("material %s lost its UVs while joining meshes" % (m.name if m else i))


def preview_material(mat, png):
    """Hook the exported colour map up in Blender too, so --save-blend/--preview show textures."""
    if not mat.node_tree:
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(png, check_existing=True)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])


def clean_name(s, used):
    s = re.sub(r"\.\d{3}$", "", s)
    s = re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_").lower() or "mat"
    s = s[:20]
    base, i = s, 2
    while s in used:
        s = "%s_%d" % (base, i)
        i += 1
    used.add(s)
    return s


# ---------------------------------------------------------------------------
# the fit


def name_blob(o):
    """Object + material + texture names/paths, lowercase - rips often only say what they are in the texture paths."""
    parts = [o.name]
    for m in (o.data.materials if o.type == "MESH" else []):
        if not m:
            continue
        parts.append(m.name)
        if m.node_tree:
            for n in m.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image:
                    # only the file + its folder, as the file originally had it (not wherever we relinked it to)
                    orig = n.image.get("fv_orig_path", n.image.filepath).replace("\\", "/")
                    parts += [n.image.name, "/".join(orig.split("/")[-2:])]
    return " ".join(parts).lower()


def import_model(path, textures=""):
    """Import a .gltf/.glb/.fbx/.dmx/.smd/.blend and return the new objects (textures relinked)."""
    before = set(bpy.data.objects.keys())
    ext = os.path.splitext(path)[1].lower()
    if ext in (".gltf", ".glb"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path, automatic_bone_orientation=False)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext in (".dmx", ".smd"):
        bpy.ops.import_scene.smd(filepath=path)
    elif ext == ".blend":
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            dst.objects = list(src.objects)
        for o in dst.objects:
            if o is not None:
                link_to_scene(o)
    else:
        die("don't know how to import " + ext)
    objs = new_objects(before)
    relink_textures(path, textures)
    return objs


def gun_axes(co, forward="", up=""):
    """Which way a gun model's barrel and top point, as unit vectors. Given ('-y', '+z') style strings they're
    used as-is; otherwise guessed from its bounding box: longest side = barrel axis, thinnest = its flat side,
    the grip is in the half that reaches furthest across the gun, and the barrel sits on top of the other half."""
    def axis(spec):
        spec = spec.strip().lower()
        v = np.zeros(3)
        v["xyz".index(spec.lstrip("+-"))] = -1.0 if spec.startswith("-") else 1.0
        return v
    if forward and up:
        d, u = axis(forward), axis(up)
        if abs(np.dot(d, u)) > 0.5:
            die("--gun-forward and --gun-up must be different axes")
        return d, u
    lo, hi = co.min(0), co.max(0)
    order = np.argsort(hi - lo)
    ax_long, ax_up = order[2], order[1]
    mid = (lo[ax_long] + hi[ax_long]) / 2
    halves = [co[co[:, ax_long] < mid], co[co[:, ax_long] >= mid]]
    reach = [np.ptp(h_[:, ax_up]) if len(h_) else 0.0 for h_ in halves]
    front = halves[int(np.argmin(reach))]
    d = np.zeros(3)
    d[ax_long] = 1.0 if np.argmin(reach) == 1 else -1.0
    u = np.zeros(3)
    u[ax_up] = 1.0 if front[:, ax_up].mean() > (lo[ax_up] + hi[ax_up]) / 2 else -1.0
    return d, u


def fit_gun(path, hero_arm, bone, grip_target, muzzle_bone, barrel_bone, scale_mult=1.0, textures="",
            forward="", up=""):
    """Import a gun model and lay it along the hero's gun: bore on the hero's barrel line, pointing at the
    muzzle bone, grip centre on grip_target (gun bind space). Returns one mesh skinned 100% to bone."""
    objs = import_model(path, textures)
    meshes = [o for o in objs if o.type == "MESH" and len(o.data.polygons)]
    if not meshes:
        die("no mesh in gun model " + path)
    for o in objs:
        o.animation_data_clear()
    for o in meshes:
        for m in list(o.modifiers):
            o.modifiers.remove(m)
        strip_shape_keys(o)
    bpy.context.view_layer.update()
    for o in meshes:
        bake_world_transform(o)
    delete(o for o in objs if o not in meshes)
    gun = meshes[0]
    if len(meshes) > 1:
        with bpy.context.temp_override(active_object=gun, selected_editable_objects=meshes, object=gun):
            bpy.ops.object.join()
    gun.name = "gun"

    co = np.empty(len(gun.data.vertices) * 3)
    gun.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    d_s, u_s = gun_axes(co, forward, up)
    side_s = np.cross(d_s, u_s)
    t = co @ d_s
    h = co @ u_s
    L = t.max() - t.min()
    # bore = centre of the muzzle face (the front 2%, minus anything poking up like a front sight)
    tip = t > t.max() - 0.02 * L
    M = d_s * t.max() + u_s * np.median(h[tip]) + side_s * np.median(co[tip] @ side_s)
    # grip = everything hanging well below the bore in the back half
    drop = (M @ u_s) - h
    sel = (drop > 0.35 * drop.max()) & (t < t.min() + 0.5 * L)
    if sel.sum() < 10:
        sel = drop > 0.35 * drop.max()
    G = co[sel].mean(0)
    G_drop = float(np.dot(M - G, u_s))
    G_back = float(np.dot(M - G, d_s))

    H = hero_arm.data.bones
    Mt = np.array(H[muzzle_bone].head_local)
    Bt = np.array(H[barrel_bone].head_local)
    Gt = np.array(grip_target)
    d_t = (Mt - Bt) / np.linalg.norm(Mt - Bt)
    u_t = (Mt - Gt) - np.dot(Mt - Gt, d_t) * d_t
    t_drop = float(np.linalg.norm(u_t))
    u_t /= t_drop
    side_t = np.cross(d_t, u_t)
    # size it so the bore lines up with the hero's bore while the palm sits on the grip
    scale = t_drop / G_drop * scale_mult
    R = np.stack([d_t, u_t, side_t], 1) @ np.stack([d_s, u_s, side_s], 0)
    out = Gt + scale * ((co - G) @ R.T)
    gun.data.vertices.foreach_set("co", out.ravel())
    gun.data.update()
    tip_t = Gt + scale * (R @ (M - G))
    log("  gun: barrel %s, up %s, scale x%.2f, muzzle ends at %s (hero muzzle %s), %.1f long (grip->muzzle %.1f)"
        % (np.round(d_s, 2), np.round(u_s, 2), scale, np.round(tip_t, 1), np.round(Mt, 1),
           scale * L, scale * G_back))

    gun.vertex_groups.clear()
    gun.vertex_groups.new(name=bone).add(list(range(len(gun.data.vertices))), 1.0, "REPLACE")
    gun.parent = hero_arm
    gun.matrix_parent_inverse = Matrix()
    gun.modifiers.new("hero", "ARMATURE").object = hero_arm
    return gun


def pick_armature(arms, meshes, pick):
    if len(arms) == 1:
        return arms[0]
    if pick:
        m = [a for a in arms if pick.lower() in a.name.lower()] or \
            [a for a in arms if any(pick.lower() in o.name.lower() for o in meshes if o.find_armature() == a)]
        if m:
            return m[0]
        die("--pick %r matched no armature. Armatures: %s" % (pick, [a.name for a in arms]))

    def score(a):
        names = " ".join([a.name.lower()] + [name_blob(o) for o in meshes if o.find_armature() == a])
        s = 0
        if re.search(r"valentine|funny|president|\bfv\b", names):
            s += 1000
        if re.search(r"d4c|dirty|deeds|stand", names):
            s -= 1000
        s += sum(len(o.data.vertices) for o in meshes if o.find_armature() == a) / 1e6
        return s

    best = max(arms, key=score)
    log("several armatures:", [a.name for a in arms], "-> using", best.name, "(override with --pick)")
    return best


def fit_matrix_rotate_z(angle):
    return Matrix.Rotation(angle, 4, "Z")


def build_warp(fv, hero, hero_spine):
    """Per-FV-bone 4x4 world matrices that move FV's joints onto the hero's joints."""
    H = hero.obj.data.bones
    W = {}
    R_of = {}

    def hpos(n):
        return H[n].head_local.copy()

    def fpos(n):
        return fv.bones[n].head_local.copy()

    def seg(fv_b, fv_child, h_b, h_child, parent_R=None):
        a, b = fpos(fv_b), (fpos(fv_child) if fv_child else None)
        ha, hb = hpos(h_b), (hpos(h_child) if h_child else None)
        if b is None or hb is None or (b - a).length < 1e-4 or (hb - ha).length < 1e-4:
            R = parent_R.copy() if parent_R is not None else Matrix.Identity(3)
            M = Matrix.Translation(ha) @ R.to_4x4() @ Matrix.Translation(-a)
            return M, R
        u = (b - a).normalized()
        # stretch so this bone's far end lands exactly on the hero's next joint; clamping it tears the mesh
        k = max(0.1, min(10.0, (hb - ha).length / (b - a).length))
        S = Matrix.Identity(3)
        for i in range(3):
            for j in range(3):
                S[i][j] += (k - 1.0) * u[i] * u[j]
        R = u.rotation_difference((hb - ha).normalized()).to_matrix()
        M = Matrix.Translation(ha) @ (R @ S).to_4x4() @ Matrix.Translation(-a)
        return M, R

    # torso: translate each joint onto the matching point of the hero's pelvis->neck line
    hips = fv.get("hips")
    neck = fv.get("neck")
    head = fv.get("head")
    h_pelvis, h_neck, h_head = hpos("pelvis"), hpos("neck_0"), hpos("head")
    if hips:
        W[hips] = Matrix.Translation(h_pelvis - fpos(hips))
    top, h_top = (neck, h_neck) if neck else (head, h_head)
    if hips and top:
        z0, z1 = fpos(hips).z, fpos(top).z
        for n in fv.spine:
            t = 0.5 if abs(z1 - z0) < 1e-4 else max(0.0, min(1.0, (fpos(n).z - z0) / (z1 - z0)))
            W[n] = Matrix.Translation(h_pelvis.lerp(h_top, t) - fpos(n))
    if neck:
        W[neck] = Matrix.Translation(h_neck - fpos(neck))
    if head:
        W[head] = Matrix.Translation(h_head - fpos(head))

    for s in SIDES:
        g = lambda c: fv.get(c, s)
        hb = lambda c: hero_bone_for(c, s, 0, H, hero_spine)
        # (bone, child it points at, parent whose rotation it inherits if the child is missing)
        chain = [("shoulder", "upperarm", None), ("upperarm", "forearm", "shoulder"), ("forearm", "hand", "upperarm"),
                 ("thigh", "shin", None), ("shin", "foot", "thigh"), ("foot", "toe", "shin")]
        for c, cc, pc in chain:
            if g(c) and hb(c):
                child_ok = g(cc) and hb(cc)
                W[g(c)], R_of[(c, s)] = seg(g(c), g(cc) if child_ok else None, hb(c), hb(cc) if child_ok else None,
                                            R_of.get((pc, s)))
        # hand points at the middle finger
        if g("hand") and hb("hand"):
            mid = fv.fingers.get(("middle", s)) or fv.fingers.get(("index", s))
            hmid = "finger_middle_0_%s" % s if mid and fv.fingers.get(("middle", s)) else "finger_index_0_%s" % s
            if mid and hmid in H:
                W[g("hand")], R_of[("hand", s)] = seg(g("hand"), mid[0], hb("hand"), hmid)
            else:
                W[g("hand")], R_of[("hand", s)] = seg(g("hand"), None, hb("hand"), None, R_of.get(("forearm", s)))
        if g("toe") and hb("toe"):
            W[g("toe")], _ = seg(g("toe"), None, hb("toe"), None, R_of.get(("foot", s)))
        # fingers
        for f, names in ((k[0], v) for k, v in fv.fingers.items() if k[1] == s):
            prevR = R_of.get(("hand", s))
            for i, n in enumerate(names):
                h = hero_bone_for("f_" + f, s, i, H, hero_spine)
                hn = hero_bone_for("f_" + f, s, i + 1, H, hero_spine)
                if not h:
                    break
                nxt = names[i + 1] if i + 1 < len(names) else None
                W[n], prevR = seg(n, nxt if hn else None, h, hn if nxt else None, prevR)
    return W


def effective_map(fv_arm, per_bone):
    """For every FV bone, the value of its nearest ancestor (or itself) that has one."""
    out = {}
    for b in fv_arm.data.bones:
        x = b
        while x is not None and x.name not in per_bone:
            x = x.parent
        out[b.name] = per_bone[x.name] if x is not None else None
    return out


def vertex_weights(obj):
    """list per vertex of (group_name, weight)."""
    names = {g.index: g.name for g in obj.vertex_groups}
    return [[(names[g.group], g.weight) for g in v.groups if g.weight > 0 and g.group in names]
            for v in obj.data.vertices]


def warp_mesh(obj, weights, Weff, fallback):
    co = np.empty(len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    out = np.empty_like(co)
    cache = {}
    for i, vw in enumerate(weights):
        acc, tot = np.zeros(3), 0.0
        for g, w in vw:
            M = Weff.get(g)
            if M is None:
                continue
            key = id(M)
            if key not in cache:
                cache[key] = np.array(M)
            m = cache[key]
            acc += w * (m[:3, :3] @ co[i] + m[:3, 3])
            tot += w
        if tot > 1e-6:
            out[i] = acc / tot
        else:
            m = np.array(fallback)
            out[i] = m[:3, :3] @ co[i] + m[:3, 3]
    obj.data.vertices.foreach_set("co", out.ravel())
    obj.data.update()


def set_weights(obj, per_vertex):
    """Replace all vertex groups; per_vertex = list of {bone: weight}. Keeps the top 4, normalised."""
    obj.vertex_groups.clear()
    groups = {}
    for vi, d in enumerate(per_vertex):
        items = sorted(d.items(), key=lambda kv: -kv[1])[:4]
        tot = sum(w for _, w in items)
        if tot <= 0:
            continue
        for bone, w in items:
            g = groups.get(bone)
            if g is None:
                g = groups[bone] = obj.vertex_groups.new(name=bone)
            g.add([vi], w / tot, "REPLACE")


def hero_weight_sampler(hero_body, skip_mats):
    """Closest-surface lookup of the hero's own skin weights (body only, not the gun)."""
    me = hero_body.data
    bm = bmesh.new()
    bm.from_mesh(me)
    mats = me.materials
    junk = [f for f in bm.faces
            if mat_has(mats[f.material_index], skip_mats)]
    bmesh.ops.delete(bm, geom=junk, context="FACES")
    bm.faces.ensure_lookup_table()
    bvh = BVHTree.FromBMesh(bm)
    names = {g.index: g.name for g in hero_body.vertex_groups}
    dl = bm.verts.layers.deform.active   # weights ride along with the verts, indices don't survive the delete

    def sample(p):
        loc, _n, fi, _d = bvh.find_nearest(p)
        if fi is None:
            return {}
        f = bm.faces[fi]
        vs = [l.vert for l in f.loops]
        ds = [max((v.co - loc).length, 1e-5) for v in vs]
        inv = [1.0 / d for d in ds]
        tot = sum(inv)
        out = {}
        for v, w in zip(vs, inv):
            for gi, bw in v[dl].items():
                if gi in names:
                    out[names[gi]] = out.get(names[gi], 0.0) + bw * w / tot
        return out

    return sample, bm


# ---------------------------------------------------------------------------


def main():
    a = parse_args()
    ensure_bst()

    if not os.path.isfile(a.model):
        die("model not found: " + a.model)
    if not os.path.isdir(a.hero_dir):
        die("hero dir not found: " + a.hero_dir)

    # addon content root = the folder that contains "models/"
    parts = a.hero_dir.replace("\\", "/").split("/")
    if "models" not in parts:
        die("--hero-dir should be inside <addon>/models/... (e.g. .../citadel_addons/fv/models/heroes_wip/doorman_v2)")
    mi = len(parts) - 1 - parts[::-1].index("models")
    addon_root = "/".join(parts[:mi])
    rel_dir = "/".join(parts[mi:])
    log("addon content root:", addon_root)

    # ---- the hero's vmdl
    vmdls = [f for f in os.listdir(a.hero_dir) if f.endswith(".vmdl")]
    vmdl = a.vmdl or (vmdls[0] if len(vmdls) == 1 else None)
    if not vmdl:
        vmdls = [f for f in vmdls if not f.startswith(OUT_NAME)]
        vmdl = max(vmdls, key=lambda f: os.path.getsize(os.path.join(a.hero_dir, f)), default=None)
    if not vmdl:
        die("no .vmdl in %s - decompile the hero model there with Source 2 Viewer first" % a.hero_dir)
    vmdl_path = os.path.join(a.hero_dir, vmdl)
    orig_path = vmdl_path + ".orig"
    if not os.path.exists(orig_path):
        shutil.copyfile(vmdl_path, orig_path)
    with open(orig_path, encoding="utf-8") as f:
        vmdl_text = f.read()
    hero_name = os.path.splitext(vmdl)[0]
    meshes = render_mesh_entries(vmdl_text)
    if not meshes:
        die("no RenderMeshFile nodes in " + vmdl)
    body = next((m for m in meshes if a.body and m["name"] == a.body), None) or \
        next((m for m in meshes if m["name"] == hero_name), None) or \
        max(meshes, key=lambda m: os.path.getsize(os.path.join(addon_root, m["filename"]))
            if os.path.exists(os.path.join(addon_root, m["filename"])) else 0)
    body_dmx = os.path.join(addon_root, body["filename"])
    if not os.path.isfile(body_dmx):
        die("body mesh %s not found - decompile the model with S2V into %s" % (body["filename"], a.hero_dir))
    log("hero:", hero_name, "| body mesh:", body["name"], "->", body["filename"])

    # ---- fresh scene + hero skeleton/body
    if bpy.app.background:
        bpy.ops.wm.read_homefile(use_empty=True)   # empty scene, keeps your add-ons/prefs
    else:
        delete(bpy.data.objects)                   # run from the Scripting tab: just clear the scene
    ensure_bst()
    before = set(bpy.data.objects.keys())
    bpy.ops.import_scene.smd(filepath=body_dmx)
    got = new_objects(before)
    hero_arm = next((o for o in got if o.type == "ARMATURE"), None)
    if hero_arm is None:
        die("the hero dmx had no skeleton?")
    hero_body = max((o for o in got if o.type == "MESH" and o.find_armature() == hero_arm),
                    key=lambda o: len(o.data.vertices))
    delete(o for o in got if o not in (hero_arm, hero_body))
    hero_arm.name = "hero_skeleton"
    hero_body.name = "hero_body"
    # BST names materials by file name only; put the full game path back (they can live in different folders)
    full = dmx_material_paths(body_dmx)
    mat_prefix = (bpy.context.scene.vs.material_path or "").strip("/")
    for m in hero_body.data.materials:
        if m and "/" not in m.name:
            want = full.get(m.name.lower()) or (mat_prefix + "/" + m.name if mat_prefix else m.name)
            m.name = want
            if m.name != want:
                log("!! material path %s is too long for this Blender version (63 chars) - use Blender 5+" % want)
    bpy.context.scene.vs.material_path = ""
    hero_bones = hero_arm.data.bones
    hero_spine = sorted([b.name for b in hero_bones if re.fullmatch(r"spine_\d+", b.name)],
                        key=lambda n: int(n.split("_")[1]))
    for need in ("pelvis", "neck_0", "head", "arm_upper_L", "hand_L", "leg_upper_L"):
        if need not in hero_bones:
            die("hero skeleton lacks '%s' - is this a Deadlock hero model?" % need)
    hero = Rig(hero_arm)
    # measure the hero without the gun/doors (they sit under the floor in the bind pose)
    body_only = hero_body.copy()
    body_only.data = hero_body.data.copy()
    link_to_scene(body_only)
    bm = bmesh.new()
    bm.from_mesh(body_only.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if mat_has(body_only.data.materials[f.material_index],
                                                                    csv(a.keep_mats))], context="FACES")
    bm.to_mesh(body_only.data)
    bm.free()
    hero_min, hero_max = world_bbox([body_only])
    delete([body_only])
    log("hero height %.1f units (floor at %.1f)" % (hero_max.z - hero_min.z, hero_min.z))

    # ---- FV import
    fv_objs = import_model(a.model, a.textures)
    fv_arms = [o for o in fv_objs if o.type == "ARMATURE"]
    fv_meshes = [o for o in fv_objs if o.type == "MESH" and len(o.data.polygons)]
    log("imported %d objects: %d armatures, %d meshes" % (len(fv_objs), len(fv_arms), len(fv_meshes)))
    for o in fv_meshes:
        arm = o.find_armature()
        log("   mesh %-40s verts=%-7d armature=%s mats=%s" % (
            o.name, len(o.data.vertices), arm.name if arm else None, [m.name for m in o.data.materials if m]))

    excl = csv(a.exclude)
    stand_meshes = []
    fv_arm = pick_armature(fv_arms, fv_meshes, a.pick) if fv_arms else None

    def excluded(o):
        return any(x in name_blob(o) for x in excl)

    def owner_armature(o):
        if o.parent and o.parent.type == "ARMATURE" and o.parent_type == "BONE":
            return o.parent
        return o.find_armature()

    keep = []
    for o in fv_meshes:
        arm = owner_armature(o)
        if fv_arm is not None and arm is not None and arm != fv_arm:
            stand_meshes.append(o)
        elif excluded(o):
            if re.search(r"d4c|dirty|deeds", o.name.lower()):
                stand_meshes.append(o)
        else:
            keep.append(o)
    if not keep:
        die("nothing left to use after --exclude/--pick; meshes were " + str([o.name for o in fv_meshes]))
    log("using %d meshes for FV, %d for the stand" % (len(keep), len(stand_meshes)))

    # stop anything posed/animated, bake every transform into the data
    for arm in fv_arms:
        arm.animation_data_clear()
        for pb in arm.pose.bones:
            pb.matrix_basis = Matrix()
    for o in keep + stand_meshes:
        o.animation_data_clear()
        strip_shape_keys(o)
    bpy.context.view_layer.update()
    # hats/props glued to a bone instead of skinned: turn that into a 100% weight
    for o in keep:
        if o.parent and o.parent.type == "ARMATURE" and o.parent_type == "BONE" and o.parent_bone:
            o.vertex_groups.clear()
            o.vertex_groups.new(name=o.parent_bone).add(list(range(len(o.data.vertices))), 1.0, "REPLACE")
    for o in keep + stand_meshes + fv_arms:
        bake_world_transform(o)
    bpy.context.view_layer.update()
    delete(o for o in fv_objs if o not in keep + stand_meshes + fv_arms)

    rig_ok = False
    fv = None
    if fv_arm is not None:
        overrides = {}
        if a.bone_map:
            import json
            with open(a.bone_map, encoding="utf-8") as f:
                overrides = json.load(f)
        fv = Rig(fv_arm, overrides)
        log("bone match:\n      " + fv.report())
        rig_ok = fv.has_limbs() and fv.get("head") and fv.get("hips")
        if not rig_ok:
            log("!! couldn't find arms/legs/head/hips in FV's rig by name - falling back to a plain scale-to-fit.")
            log("   Fix it with --bone-map (see README) for a proper fit.")

    # ---- global fit: face +X, feet on the floor, head at the hero's head height
    fv_min, fv_max = world_bbox(keep)
    if rig_ok:
        fwd = Vector((0, 0, 0))
        for s in SIDES:
            foot, toe = fv.get("foot", s), fv.get("toe", s)
            if foot and toe:
                fwd += fv.head_pos(toe) - fv.head_pos(foot)
        fwd.z = 0
        if fwd.length < 1e-4:
            fwd = Vector((0, -1, 0))
        # left side should end up at +Y
        side_vec = fv.head_pos(fv.get("upperarm", "L")) - fv.head_pos(fv.get("upperarm", "R"))
        ang = -math.atan2(fwd.y, fwd.x)
        rot = fit_matrix_rotate_z(ang)
        if (rot.to_3x3() @ side_vec).y < 0:
            log("!! left/right look swapped in FV's rig - check the preview")
        fv_head_h = fv.head_pos(fv.get("head")).z - fv_min.z
        hero_head_h = hero.head_pos("head").z - hero_min.z
        scale = hero_head_h / max(fv_head_h, 1e-4) * a.scale
        piv = fv.head_pos(fv.get("hips"))
        target = hero.head_pos("pelvis")
    else:
        ang = -math.atan2(-1, 0)   # glTF/Blender convention: characters look down -Y
        rot = fit_matrix_rotate_z(ang)
        scale = (hero_max.z - hero_min.z) / max(fv_max.z - fv_min.z, 1e-4) * a.scale
        piv = Vector(((fv_min.x + fv_max.x) / 2, (fv_min.y + fv_max.y) / 2, fv_min.z))
        target = Vector((hero.head_pos("pelvis").x, hero.head_pos("pelvis").y, hero_min.z))
    G = Matrix.Translation(Vector((target.x, target.y, hero_min.z))) @ Matrix.Scale(scale, 4) @ rot @ \
        Matrix.Translation(-Vector((piv.x, piv.y, fv_min.z)))
    log("global fit: rotate %.1f deg, scale x%.3f" % (math.degrees(ang), scale))
    for o in keep + ([fv_arm] if fv_arm else []):
        o.matrix_world = G @ o.matrix_world
        bake_world_transform(o)
    bpy.context.view_layer.update()

    # ---- per-joint warp onto the hero skeleton
    weights_mode = a.weights
    if weights_mode == "auto":
        weights_mode = "model" if rig_ok else "hero"
    if rig_ok:
        W = build_warp(fv, hero, hero_spine)
        Weff = effective_map(fv_arm, W)
        fallback = W.get(fv.get("hips"), Matrix())
        for o in keep:
            warp_mesh(o, vertex_weights(o), Weff, fallback)
        log("warped %d meshes onto %d hero joints" % (len(keep), len(W)))

    # ---- skin weights onto hero bones
    if weights_mode == "model" and rig_ok:
        per_bone = {}
        for b in fv_arm.data.bones:
            c, s = fv.cls.get(b.name, (None, None))
            if b.name in fv.overrides:
                per_bone[b.name] = fv.overrides[b.name]
                continue
            if not c:
                continue
            if c == "spine":
                i = fv.spine.index(b.name)
                n = len(fv.spine)
                j = round(i * (len(hero_spine) - 1) / (n - 1)) if n > 1 else len(hero_spine) // 2
                hname = hero_bone_for("spine", None, j, hero_bones, hero_spine)
            elif c.startswith("f_"):
                names = fv.fingers.get((c[2:], s), [])
                if b.name not in names:
                    continue
                hname = hero_bone_for(c, s, names.index(b.name), hero_bones, hero_spine)
            elif c in ("hips", "neck", "head", "jaw"):
                if b.name != fv.get(c) and c != "jaw":
                    continue
                hname = hero_bone_for(c, None, 0, hero_bones, hero_spine)
            else:
                hname = hero_bone_for(c, s, 0, hero_bones, hero_spine) if s else None
            if hname:
                per_bone[b.name] = hname
        eff = effective_map(fv_arm, per_bone)
        for o in keep:
            new = []
            for vw in vertex_weights(o):
                d = {}
                for g, w in vw:
                    hb = eff.get(g) or ("pelvis" if g in fv_arm.data.bones else None)
                    if hb:
                        d[hb] = d.get(hb, 0.0) + w
                new.append(d or {"pelvis": 1.0})
            set_weights(o, new)
        log("skin weights: FV's own, renamed onto hero bones")
    else:
        sample, bm = hero_weight_sampler(hero_body, csv(a.keep_mats))
        for o in keep:
            mw = o.matrix_world
            set_weights(o, [sample(mw @ v.co) or {"pelvis": 1.0} for v in o.data.vertices])
        bm.free()
        log("skin weights: copied from the hero's body by proximity")

    for o in keep:
        for m in list(o.modifiers):
            if m.type == "ARMATURE":
                o.modifiers.remove(m)
        o.parent = hero_arm
        o.matrix_parent_inverse = Matrix()
        o.modifiers.new("hero", "ARMATURE").object = hero_arm

    # ---- optional D4C: rigid, floating over his shoulder
    if a.with_stand and stand_meshes:
        for o in stand_meshes:
            for m in list(o.modifiers):
                if m.type == "ARMATURE":
                    o.modifiers.remove(m)
        smin, smax = world_bbox(stand_meshes)
        s_scale = (hero_max.z - hero_min.z) * 1.1 / max(smax.z - smin.z, 1e-4)
        s_piv = Vector(((smin.x + smax.x) / 2, (smin.y + smax.y) / 2, smin.z))
        pel = hero.head_pos("pelvis")
        S = Matrix.Translation(Vector((pel.x - 28, pel.y - 10, hero_min.z + 14))) @ Matrix.Scale(s_scale, 4) @ \
            rot @ Matrix.Translation(-s_piv)
        for o in stand_meshes:
            o.matrix_world = S @ o.matrix_world
            bake_world_transform(o)
            set_weights(o, [{"spine_1" if "spine_1" in hero_bones else "pelvis": 1.0}] * len(o.data.vertices))
            o.parent = hero_arm
            o.matrix_parent_inverse = Matrix()
            o.modifiers.new("hero", "ARMATURE").object = hero_arm
        keep += stand_meshes
        log("D4C added behind him (%d meshes)" % len(stand_meshes))
    else:
        delete(stand_meshes)
    if fv_arm:
        delete(fv_arms)

    # ---- hero parts we keep (gun, doors)
    keep_mats = csv(a.keep_mats)
    if a.gun:
        # the bone the stock gun hangs off = the one most of its vertices follow
        gun_words = {"gun", "weapon"}
        mats_ = hero_body.data.materials
        names_ = {g.index: g.name for g in hero_body.vertex_groups}
        tally = {}
        for poly in hero_body.data.polygons:
            if not mat_has(mats_[poly.material_index], gun_words):
                continue
            for vi in poly.vertices:
                for g in hero_body.data.vertices[vi].groups:
                    tally[names_[g.group]] = tally.get(names_[g.group], 0.0) + g.weight
        gun_bone = max(tally, key=tally.get) if tally else "weapon"
        keep_mats = [k for k in keep_mats if k not in gun_words]
        new_gun = fit_gun(os.path.abspath(a.gun), hero_arm, gun_bone,
                          [float(x) for x in a.gun_grip.split(",")],
                          "muzzle_fx" if "muzzle_fx" in hero_bones else "weaponTip",
                          "barrel_a" if "barrel_a" in hero_bones else "weapon",
                          a.gun_scale, a.textures, a.gun_forward, a.gun_up)
        keep.append(new_gun)
        log("replaced the hero's gun with %s (follows %s)" % (os.path.basename(a.gun), gun_bone))
    gun = hero_body.copy()
    gun.data = hero_body.data.copy()
    link_to_scene(gun)
    bm = bmesh.new()
    bm.from_mesh(gun.data)
    mats = gun.data.materials
    kill = [f for f in bm.faces
            if not mat_has(mats[f.material_index], keep_mats)]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bm.to_mesh(gun.data)
    bm.free()
    kept_names = sorted({gun.data.materials[p.material_index].name for p in gun.data.polygons})
    if len(gun.data.polygons):
        keep.append(gun)
        log("kept from the hero body:", kept_names)
    else:
        delete([gun])

    # ---- materials -> vmat + png
    out_mat_dir = os.path.join(addon_root, MAT_DIR)
    os.makedirs(out_mat_dir, exist_ok=True)
    used, done = set(), {}
    for o in keep:
        if o == gun:
            continue
        if not o.data.materials:
            o.data.materials.append(bpy.data.materials.new("fv_default"))
        for i, m in enumerate(o.data.materials):
            key = m.name if m else "none"
            if key in done:
                o.data.materials[i] = done[key]
                continue
            img, rgba = base_color_source(m)
            # rips have names like "25_7vtn11t0 body_0.1_16_16"; the texture name ("Diffuse", "Eyes") reads better
            label = os.path.splitext(img.name)[0] if img else (m.name if m else "default")
            if img and label.lower() in ("diffuse", "albedo", "basecolor", "base_color", "color", "texture"):
                label = "body"
            short = clean_name(label, used)
            color_png = "fv_%s_color.png" % short
            path = os.path.join(out_mat_dir, color_png)
            if not (img and save_image(img, path)):
                write_png(path, 4, 4, [rgba[0], rgba[1], rgba[2], 1.0] * 16)
            vmat_rel = "%s/fv_%s.vmat" % (MAT_DIR, short)
            with open(os.path.join(addon_root, vmat_rel), "w", encoding="utf-8") as f:
                f.write(VMAT_TEMPLATE.format(color="%s/%s" % (MAT_DIR, color_png), backfaces=1))
            nm = bpy.data.materials.new(vmat_rel)
            if nm.name != vmat_rel:
                die("material path too long for Blender: " + vmat_rel)
            preview_material(nm, path)
            done[key] = nm
            o.data.materials[i] = nm
            log("  material %-28s -> %s%s" % (key, vmat_rel, "" if img else " (flat colour)"))

    # ---- one object, exported with BST
    # Every part needs exactly one UV map with the same name, or join keeps them as separate
    # maps and BST exports only one: FV's "UV1" vs the gun's "texcoord$0" left FV with all-zero UVs.
    for o in keep:
        me = o.data
        if not me.uv_layers:
            me.uv_layers.new(name="UVMap")
            continue
        main = next((l.name for l in me.uv_layers if l.active_render), me.uv_layers.active.name)
        for name in [l.name for l in me.uv_layers if l.name != main]:
            me.uv_layers.remove(me.uv_layers[name])
        me.uv_layers[0].name = "UVMap"
    for o in keep:
        o.select_set(True)
    final = keep[0]
    with bpy.context.temp_override(active_object=final, selected_editable_objects=keep, object=final):
        bpy.ops.object.join()
    final.name = OUT_NAME
    final.data.name = OUT_NAME
    check_uvs(final)
    delete([hero_body])
    col = bpy.data.collections.new(OUT_NAME)
    bpy.context.scene.collection.children.link(col)
    for c in list(final.users_collection):
        c.objects.unlink(final)
    col.objects.link(final)

    sc = bpy.context.scene
    sc.vs.export_path = a.hero_dir + os.sep
    sc.vs.export_format = "DMX"
    sc.vs.dmx_encoding = "9"
    sc.vs.dmx_format = "22_modeldoc"
    sc.vs.material_path = ""
    col.vs.subdir = ""

    if a.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.save_blend), copy=True)
        log("saved", a.save_blend)
    if a.preview:
        render_preview(final, hero_arm, a.preview)

    r = bpy.ops.export_scene.smd(collection=OUT_NAME)
    dmx_out = os.path.join(a.hero_dir, OUT_NAME + ".dmx")
    if "FINISHED" not in r or not os.path.isfile(dmx_out):
        die("DMX export failed (see Blender Source Tools output above)")
    log("wrote", dmx_out)

    # ---- patch the vmdl
    text = vmdl_text
    drops = csv(a.drop)
    dmx_rel = "%s/%s.dmx" % (rel_dir, OUT_NAME)
    for m in sorted(render_mesh_entries(text), key=lambda m: -m["start"]):
        if m["filename"] == body["filename"]:
            blk = text[m["start"]:m["end"]]
            blk = blk.replace('"%s"' % m["filename"], '"%s"' % dmx_rel)
            text = text[:m["start"]] + blk + text[m["end"]:]
        elif any(d in m["name"].lower() or d in os.path.basename(m["filename"]).lower() for d in drops):
            text = remove_block(text, m["start"], m["end"])
            log("removed render mesh", m["name"])
    with open(vmdl_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    log("patched", vmdl_path, "(original kept as %s)" % os.path.basename(orig_path))
    log("done - now compile %s with the Deadlock VMDL Compiler (hero preset: %s) and make the vpk" % (vmdl, hero_name))


# ---------------------------------------------------------------------------
# preview (Cycles, CPU) - only when --preview is given


def render_preview(obj, arm, prefix):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 24
    sc.render.resolution_x, sc.render.resolution_y = 640, 900
    sc.render.film_transparent = False
    world = bpy.data.worlds.new("fv") if not sc.world else sc.world
    sc.world = world
    if not world.node_tree:
        world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.35, 0.33, 0.4, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    mn, mx = world_bbox([obj])
    h = mx.z - mn.z
    c = (mn + mx) / 2
    light = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    light.data.energy = 3
    light.rotation_euler = (math.radians(40), math.radians(10), math.radians(30))
    sc.collection.objects.link(light)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = h * 1.15
    sc.collection.objects.link(cam)
    sc.camera = cam
    for tag, loc in (("front", (c.x + 300, c.y, c.z)), ("side", (c.x, c.y + 300, c.z))):
        cam.location = loc
        d = Vector((c.x, c.y, c.z)) - Vector(loc)
        cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = "%s_%s.png" % (prefix, tag)
        bpy.ops.render.render(write_still=True)
        log("preview ->", sc.render.filepath)
    delete([light, cam])


if __name__ == "__main__":
    main()
