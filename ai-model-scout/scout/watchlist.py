"""Known-good open music models that are always checked, even in a quiet week.

Discovery finds new things; this list makes sure the established tools you'd
actually use stay in the report so you can see when they get updated.
"""

MUSIC_HF = [
    "ACE-Step/ACE-Step-v1-3.5B",         # full songs with vocals from lyrics + style tags
    "m-a-p/YuE-s1-7B-anneal-en-cot",     # lyrics-to-song, long form
    "ASLP-lab/DiffRhythm-full",          # fast full-song diffusion
    "stabilityai/stable-audio-open-1.0", # samples, loops, sound design
    "facebook/musicgen-large",           # instrumental generation (weights CC-BY-NC)
    "facebook/musicgen-melody",          # melody-conditioned generation
    "m-a-p/MERT-v1-330M",                # music understanding embeddings
]

MUSIC_GITHUB = [
    "spotify/basic-pitch",               # audio -> MIDI transcription
    "facebookresearch/demucs",           # stem separation
    "magenta/mt3",                       # multi-instrument transcription
    "mir-aidj/all-in-one",               # beats, downbeats, sections, tempo
    "CPJKU/madmom",                      # beat/onset/chord analysis
    "MTG/essentia",                      # music analysis library + models
    "BreezeWhite/oemer",                 # sheet music image -> MusicXML (OMR)
]
