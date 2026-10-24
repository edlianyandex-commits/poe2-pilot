from pathlib import Path

from pilot.core.logpath import candidate_paths, find_client_log, parse_library_folders

VDF = '''"libraryfolders"
{
	"0"
	{
		"path"		"C:\\\\Program Files (x86)\\\\Steam"
	}
	"1"
	{
		"path"		"D:\\\\SteamLibrary"
	}
}'''


def test_parse_vdf():
    assert parse_library_folders(VDF) == [Path(r"C:\Program Files (x86)\Steam"), Path(r"D:\SteamLibrary")]


def test_find_in_other_library(tmp_path):
    steam = tmp_path / "Steam"
    (steam / "steamapps").mkdir(parents=True)
    lib = tmp_path / "Lib"
    log = lib / "steamapps" / "common" / "Path of Exile 2" / "logs" / "Client.txt"
    log.parent.mkdir(parents=True)
    log.write_text("x", encoding="utf-8")
    vdf = '"libraryfolders" { "1" { "path" "%s" } }' % str(lib).replace("\\", "\\\\")
    (steam / "steamapps" / "libraryfolders.vdf").write_text(vdf, encoding="utf-8")
    assert log in candidate_paths([steam])
    assert find_client_log([steam]) == log

