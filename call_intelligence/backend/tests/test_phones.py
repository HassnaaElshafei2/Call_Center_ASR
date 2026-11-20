from callintel.services import phones


def test_normalize_formats():
    for raw in ["01272729111", "201272729111", "1272729111", "+20 127 272 9111", "٠١٢٧٢٧٢٩١١١", "00201272729111"]:
        assert phones.normalize(raw) == "+201272729111", raw


def test_normalize_rejects_non_mobiles():
    for raw in ["", "12345", "0225551234", "01972729111", "abc"]:
        assert phones.normalize(raw) is None, raw


def test_from_filename_with_and_without_rules():
    assert phones.from_filename("btech_01011223344.wav") == "+201011223344"
    assert phones.from_filename("rec_2026-11-01_1000470080.mp3") == "+201000470080"
    assert phones.from_filename("ADIB-REC-77812.wav") is None
    rules = [{"pattern": r"btech_(?P<phone>\d{10,12})"}]
    assert phones.from_filename("btech_201029240321.wav", rules) == "+201029240321"


def test_mask_and_hash():
    assert phones.mask("+201029240321") == "+20 10 •••• 0321"
    assert phones.hash_phone("+201029240321") == phones.hash_phone("+201029240321")
    assert phones.hash_phone("+201029240321") != phones.hash_phone("+201029240322")
