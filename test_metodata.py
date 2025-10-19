# test_metadata.py
from backend.processors.metadata_processor import create_metadata_processor

mp = create_metadata_processor()

samples = [
    "Korol_i_SHut_-_Lesnik.mp3",
    "Artur_Pirozhkov_-_Samo_Soboj.mp3",
    "Ramil_-_Chto_U_Nee_Vnutri.mp3",
    "Sqwoz_Bab_-_Romantic.mp3",
    "GAYAZOV_BROTHER_-_Pyanyjj_Tuman.mp3"
]

for s in samples:
    res = mp.process(s)
    print(f"{s} -> artist: {res.get('artist')!r}, title: {res.get('title')!r}")
