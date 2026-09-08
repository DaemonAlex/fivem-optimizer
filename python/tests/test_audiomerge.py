"""audiomerge: one audio resource (or several) -> one resource with one registration per data type."""
import glob
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import relmerge

CORPUS = os.environ.get("AUDIO_FIXTURES", "")
CLI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "audiomerge.py")
needs_corpus = pytest.mark.skipif(not CORPUS or not os.path.isdir(os.path.join(CORPUS, "gb_vehicles_audio")), reason="set AUDIO_FIXTURES")


@pytest.fixture
def source(tmp_path):
    """A copy of the Gabz audio resource with fake wave files named from the sound data."""
    src = tmp_path / "gb_vehicles_audio"
    shutil.copytree(os.path.join(CORPUS, "gb_vehicles_audio"), src)
    for f in glob.glob(str(src / "audioconfig" / "*_sounds.dat54.rel")):
        r = relmerge.parse(open(f, "rb").read())
        for n in r.names:
            if "\\" in n and n.lower().startswith("dlc_"):
                pack, wave = n.split("\\", 1)
                d = src / "sfx" / pack.lower()
                d.mkdir(parents=True, exist_ok=True)
                (d / f"{wave.lower()}.awc").write_bytes(b"AWC!" + wave.encode())
    return src


@needs_corpus
def test_build_merged_resource(source, tmp_path):
    out = tmp_path / "gb_audio"
    res = subprocess.run([sys.executable, CLI, str(source), "--out", str(out), "--name", "gbaudio", "--max-waves-per-pack", "500"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr + res.stdout
    assert (out / "fxmanifest.lua").exists()
    manifest = (out / "fxmanifest.lua").read_text()
    assert manifest.count("AUDIO_GAMEDATA") == 1 and manifest.count("AUDIO_SOUNDDATA") == 1 and manifest.count("AUDIO_WAVEPACK") == 1
    assert "audioconfig/gbaudio_game.dat" in manifest and "sfx/dlc_gbaudio" in manifest
    assert (out / "audioconfig" / "gbaudio_game.dat151.rel").exists()
    assert (out / "audioconfig" / "gbaudio_sounds.dat54.rel").exists()
    waves = os.listdir(out / "sfx" / "dlc_gbaudio")
    assert len(waves) == len(glob.glob(str(source / "sfx" / "*" / "*.awc")))
    # every source sound item is in the merged file and every wave reference points at the new folder
    merged = relmerge.parse((out / "audioconfig" / "gbaudio_sounds.dat54.rel").read_bytes())
    have = {h for h, _o, _l in merged.index}
    for f in glob.glob(str(source / "audioconfig" / "*_sounds.dat54.rel")):
        for h, _o, _l in relmerge.parse(open(f, "rb").read()).index:
            assert h in have
    expected = {relmerge.joaat("dlc_gbaudio/" + w[:-4]) for w in waves}
    refs = set(merged.pack_refs())
    assert refs & expected and not any(relmerge.joaat("dlc_gb811s2/gb811s2") == r for r in refs)
    assert "registrations before -> after" in res.stdout and "AUDIO_GAMEDATA" in res.stdout


@needs_corpus
def test_only_declared_files_are_merged(source, tmp_path):
    # the Gabz manifest never declares its amp (synth) files, so the merged resource must not either
    out = tmp_path / "gb_audio"
    res = subprocess.run([sys.executable, CLI, str(source), "--out", str(out), "--name", "gbaudio"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert not (out / "audioconfig" / "gbaudio_amp.dat10.rel").exists()
    assert "AUDIO_SYNTHDATA" not in (out / "fxmanifest.lua").read_text()


@needs_corpus
def test_refuses_to_overwrite_and_writes_report(source, tmp_path):
    out = tmp_path / "gb_audio"
    subprocess.run([sys.executable, CLI, str(source), "--out", str(out), "--name", "gbaudio"], capture_output=True, text=True)
    res = subprocess.run([sys.executable, CLI, str(source), "--out", str(out), "--name", "gbaudio"], capture_output=True, text=True)
    assert res.returncode != 0 and "exists" in (res.stderr + res.stdout).lower()
    assert (out / "MERGE-REPORT.txt").exists()
    report = (out / "MERGE-REPORT.txt").read_text()
    assert "conflict" in report.lower() and "wave" in report.lower()


@needs_corpus
def test_waves_can_be_split_across_several_packs(source, tmp_path):
    out = tmp_path / "gb_audio"
    res = subprocess.run([sys.executable, CLI, str(source), "--out", str(out), "--name", "gbaudio", "--max-waves-per-pack", "40"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr + res.stdout
    packs = sorted(p for p in os.listdir(out / "sfx") if p.startswith("dlc_gbaudio"))
    assert len(packs) >= 3 and all(len(os.listdir(out / "sfx" / p)) <= 40 for p in packs)
    manifest = (out / "fxmanifest.lua").read_text()
    assert manifest.count("AUDIO_WAVEPACK") == len(packs)
    merged = relmerge.parse((out / "audioconfig" / "gbaudio_sounds.dat54.rel").read_bytes())
    refs = set(merged.pack_refs())
    # every wave is referenced under the folder it actually sits in
    for p in packs:
        for w in os.listdir(out / "sfx" / p):
            assert relmerge.joaat(f"{p}/{w[:-4]}") in refs, (p, w)


@needs_corpus
def test_synth_data_can_be_kept_unmerged(source, tmp_path):
    # give the source two declared synth files so the option has something to keep
    manifest = source / "fxmanifest.lua"
    text = manifest.read_text()
    text += "\ndata_file 'AUDIO_SYNTHDATA' 'audioconfig/gb811s2_amp.dat'\ndata_file 'AUDIO_SYNTHDATA' 'audioconfig/gbargento7f_amp.dat'\n"
    manifest.write_text(text)
    out = tmp_path / "gb_audio"
    res = subprocess.run([sys.executable, CLI, str(source), "--out", str(out), "--name", "gbaudio", "--keep-synth"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr + res.stdout
    m = (out / "fxmanifest.lua").read_text()
    assert m.count("AUDIO_SYNTHDATA") == 2 and "gb811s2_amp.dat'" in m
    assert (out / "audioconfig" / "gb811s2_amp.dat10.rel").exists()
    assert not (out / "audioconfig" / "gbaudio_amp.dat10.rel").exists()
