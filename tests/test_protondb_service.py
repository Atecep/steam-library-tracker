import time
import unittest
from unittest.mock import Mock, patch

import requests

import protondb_service as protondb


def report(command, timestamp=None, notes="", verdict="yes"):
    return {
        "timestamp": timestamp or int(time.time()),
        "responses": {
            "verdict": verdict,
            "launchOptions": command,
            "notes": {"verdict": notes},
        },
    }


class ProtonDBServiceTests(unittest.TestCase):
    def test_opposite_assignment_values_have_separate_families(self):
        pairs = (
            ("SteamDeck=0", "SteamDeck=1"),
            ("PROTON_NO_ESYNC=0", "PROTON_NO_ESYNC=1"),
            ("DXVK_ASYNC=0", "DXVK_ASYNC=1"),
            ("VKD3D_CONFIG=dxr", "VKD3D_CONFIG=nodxr"),
            ("DRI_PRIME=0", "DRI_PRIME=1"),
            ("WINEDLLOVERRIDES=dxgi=n,b", "WINEDLLOVERRIDES=dxgi=b,n"),
        )
        for first, second in pairs:
            with self.subTest(first=first, second=second):
                first_key = protondb._command_semantics(
                    f"{first} %command%"
                )["family_key"]
                second_key = protondb._command_semantics(
                    f"{second} %command%"
                )["family_key"]
                self.assertNotEqual(first_key, second_key)

    def test_equivalent_variants_still_share_a_family(self):
        commands = (
            'PROTON_NO_ESYNC="1" TZ=UTC %command% --launcher-skip',
            "TZ=UTC PROTON_NO_ESYNC=1 gamemoderun %command% --launcher-skip",
        )
        result = protondb._analyse_reports(
            [report(command) for command in commands],
            {"gpu_vendors": []},
        )
        self.assertEqual(len(result["ranked_options"]), 1)
        self.assertEqual(result["ranked_options"][0]["count"], 2)
        self.assertEqual(len(result["ranked_options"][0]["variants"]), 2)

    def test_steamdeck_zero_and_one_are_counted_separately(self):
        result = protondb._analyse_reports(
            [report("SteamDeck=0 %command%"), report("SteamDeck=1 %command%")],
            {"gpu_vendors": []},
        )
        self.assertEqual(len(result["ranked_options"]), 2)
        self.assertEqual(
            {item["count"] for item in result["ranked_options"]}, {1}
        )

    def test_text_mentions_are_not_extracted_as_commands(self):
        sample = (
            "The fix is to add PROTON_NO_ESYNC=1 to launch options.\n"
            "PROTON_ENABLE_HDR=1 launch option was absolutely needed.\n"
            "I tried %command% -dx11 yesterday.\n"
            "gamescope and config hypr-user.lua worked well."
        )
        self.assertEqual(protondb._command_candidates_from_text(sample), [])

    def test_code_spans_and_bare_options_in_notes_remain_available(self):
        item = report(
            "",
            notes="Try `RADV_PERFTEST=nosam` or `SteamDeck=0 %command%`.",
        )
        self.assertEqual(
            protondb._extract_launch_options(item),
            ["RADV_PERFTEST=nosam", "SteamDeck=0 %command%"],
        )

    def test_structured_options_take_precedence_over_note_mentions(self):
        item = report(
            "TZ=UTC %command% --launcher-skip",
            notes="I set `TZ=UTC` and launched the game.",
        )
        self.assertEqual(
            protondb._extract_launch_options(item),
            ["TZ=UTC %command% --launcher-skip"],
        )

    def test_arguments_after_command_marker_are_preserved(self):
        command = "gamescope -W 1920 -H 1080 -- %command% -dx11"
        self.assertEqual(
            protondb._command_candidates_from_text(f"Launch options: {command}"),
            [command],
        )
        self.assertEqual(
            protondb._command_candidates_from_text("-dx11 %command%"),
            ["-dx11 %command%"],
        )
        self.assertEqual(
            protondb._extract_launch_options(report("--launcher-skip -fullscreen")),
            ["--launcher-skip -fullscreen"],
        )
        self.assertEqual(
            protondb._extract_launch_options(
                report("WINEDLLOVERRIDES=\"dsound=n,b\" %command% +noIntroCinematics")
            ),
            ['WINEDLLOVERRIDES="dsound=n,b" %command% +noIntroCinematics'],
        )

    def test_quoted_dll_override_separator_is_allowed(self):
        command = (
            'WINEDLLOVERRIDES="version=n,b;winmm=n,b" '
            "%command% --launcher-skip"
        )
        self.assertEqual(protondb._command_candidates_from_text(command), [command])
        self.assertEqual(
            protondb._extract_launch_options(report("%command% config.cfg extra")),
            [],
        )
        self.assertTrue(protondb._is_safe_to_surface(command))
        self.assertEqual(
            protondb._command_candidates_from_text(
                'WINEDLLOVERRIDES="winmm, icuin,icuuc=n,b" %command%'
            ),
            ['WINEDLLOVERRIDES="winmm, icuin,icuuc=n,b" %command%'],
        )
        self.assertFalse(
            protondb._is_safe_to_surface("PROTON_NO_ESYNC=1; rm -rf / %command%")
        )
        self.assertFalse(
            protondb._is_safe_to_surface("PROTON_NO_ESYNC=1 && touch /tmp/x")
        )

    def test_normalisation_preserves_assignment_quotes(self):
        command = 'WINEDLLOVERRIDES="version=n,b"'
        self.assertEqual(protondb._normalise_command(command), command)
        self.assertTrue(protondb._is_safe_to_surface(command))
        self.assertEqual(
            protondb._normalise_command('"PROTON_NO_ESYNC=1 %command%"'),
            "PROTON_NO_ESYNC=1 %command%",
        )

    def test_vendor_filter_is_skipped_when_gpu_is_unknown(self):
        reports = [
            report("RADV_PERFTEST=rt %command%"),
            report("PROTON_HIDE_NVIDIA_GPU=1 %command%"),
            report("PROTON_ENABLE_NVAPI=1 %command%"),
        ]
        amd_result = protondb._analyse_reports(
            reports, {"gpu_vendors": ["AMD"]}
        )
        unknown_result = protondb._analyse_reports(
            reports, {"gpu_vendors": []}
        )
        self.assertEqual(len(amd_result["ranked_options"]), 1)
        self.assertEqual(len(unknown_result["ranked_options"]), 3)

    def test_repeated_assignments_use_last_value(self):
        first = "SteamDeck=0 SteamDeck=1 %command%"
        second = "SteamDeck=1 SteamDeck=0 %command%"
        result = protondb._analyse_reports(
            [report(first), report(second), report("SteamDeck=1 %command%")],
            {"gpu_vendors": []},
        )
        self.assertEqual(len(result["ranked_options"]), 2)
        self.assertEqual(sorted(item["count"] for item in result["ranked_options"]), [1, 2])
        self.assertEqual(protondb._assignment_value(first, "SteamDeck"), "1")
        self.assertEqual(protondb._assignment_value(second, "SteamDeck"), "0")

    def test_case_and_meaningful_arguments_are_not_combined(self):
        pairs = (
            ("PROTON_NO_ESYNC=1 %command% -dx11", "PROTON_NO_ESYNC=1 %command% -dx12"),
            ("gamescope -f -- %command%", "gamescope -b -- %command%"),
            ("PROTON_NO_ESYNC=1 Foo=ABC %command%", "PROTON_NO_ESYNC=1 foo=ABC %command%"),
            ("PROTON_NO_ESYNC=1 Foo=ABC %command%", "PROTON_NO_ESYNC=1 Foo=abc %command%"),
            ("%command% --profile Game", "%command% --profile game"),
        )
        for first, second in pairs:
            with self.subTest(first=first, second=second):
                result = protondb._analyse_reports(
                    [report(first), report(second)], {"gpu_vendors": []}
                )
                self.assertEqual(len(result["ranked_options"]), 2)
                self.assertEqual([item["count"] for item in result["ranked_options"]], [1, 1])

    def test_assignments_after_marker_are_game_arguments(self):
        command = "PROTON_NO_ESYNC=1 %command% --setting SteamDeck=0"
        self.assertIsNone(protondb._assignment_value(command, "SteamDeck"))
        result = protondb._analyse_reports(
            [report(command), report(command.replace("SteamDeck=0", "SteamDeck=1"))],
            {"gpu_vendors": []},
        )
        self.assertEqual(len(result["ranked_options"]), 2)

    def test_steamdeck_does_not_erase_other_gpu_requirements(self):
        reports = [
            report("SteamDeck=0 %command%"),
            report("SteamDeck=0 RADV_PERFTEST=rt %command%"),
            report("SteamDeck=0 PROTON_ENABLE_NVAPI=1 %command%"),
        ]
        for vendor, expected in (("AMD", "RADV_PERFTEST"), ("NVIDIA", "PROTON_ENABLE_NVAPI")):
            with self.subTest(vendor=vendor):
                result = protondb._analyse_reports(reports, {"gpu_vendors": [vendor]})
                commands = {item["command"] for item in result["ranked_options"]}
                self.assertEqual(len(commands), 2)
                self.assertIn("SteamDeck=0 %command%", commands)
                self.assertTrue(any(expected in command for command in commands))
        self.assertEqual(len(protondb._analyse_reports(reports, {"gpu_vendors": []})["ranked_options"]), 3)

    def test_multiple_argument_values_and_mixed_code_notes(self):
        command = "%command% +set r_mode 5"
        self.assertEqual(protondb._extract_launch_options(report(command)), [command])
        self.assertEqual(protondb._command_candidates_from_text(command), [command])
        self.assertEqual(
            protondb._command_candidates_from_text("Launch options: %command% --profiles a b"),
            ["%command% --profiles a b"],
        )
        self.assertEqual(protondb._command_candidates_from_text("gamescope -f worked perfectly"), [])
        notes = "Use `Proton` as described above.\nSteamDeck=0 %command%"
        self.assertEqual(protondb._extract_launch_options(report("", notes=notes)), ["SteamDeck=0 %command%"])
        notes = "Try `PROTON_NO_ESYNC=1 %command%`.\n" + command
        self.assertEqual(
            protondb._extract_launch_options(report("", notes=notes)),
            ["PROTON_NO_ESYNC=1 %command%", command],
        )

    def test_normalisation_preserves_quoted_spacing_and_argument_punctuation(self):
        commands = (
            'FOO="a  b" %command%',
            "FOO='a\tb' %command%",
            "%command% --profile game.",
            "%command% --list a,b,",
            'FOO="% command %" %command%',
            r"FOO=a\ b %command%",
            r"FOO=a\  %command%",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(protondb._normalise_command(command), command)
                self.assertEqual(protondb._extract_launch_options(report(command)), [command])
        self.assertEqual(protondb._normalise_command("FOO=1   %command%   -dx11"), "FOO=1 %command% -dx11")

    def test_placeholder_alone_is_not_a_useful_option(self):
        for text in ("%command%", "Leave `%command%` as the placeholder."):
            with self.subTest(text=text):
                self.assertEqual(protondb._extract_launch_options(report(text)), [])
        self.assertEqual(protondb._analyse_reports([report("%command%")], {})["ranked_options"], [])

    def test_recency_frequency_and_positive_verdict_are_preserved(self):
        old = int(time.time()) - 900 * 86400
        reports = [report("%command% -dx11", timestamp=old) for _ in range(5)]
        reports += [report("%command% -dx12"), report("%command% -broken", verdict="no")]
        ranked = protondb._analyse_reports(reports, {})["ranked_options"]
        self.assertEqual([item["command"] for item in ranked], ["%command% -dx12", "%command% -dx11"])
        self.assertEqual([item["score"] for item in ranked], [4.0, 2.5])

    def test_narrative_after_marker_is_not_ranked_in_any_text_context(self):
        commands = (
            "%command% works great on Linux",
            "%command% will run fine",
            "%command% --launcher-skip works great",
            "%command% -dx11 works",
            "%command% +set r_mode 5 works great",
            "%command% /WineDetectionEnabled:False works great",
        )
        for command in commands:
            for text in (command, f"Launch options: {command}", f"`{command}`"):
                with self.subTest(text=text):
                    item = report(text)
                    self.assertEqual(protondb._extract_launch_options(item), [])
                    self.assertEqual(protondb._extract_launch_options(report("", notes=text)), [])
                    self.assertEqual(protondb._analyse_reports([item], {})["ranked_options"], [])

    def test_structured_game_arguments_remain_available(self):
        commands = (
            "%command% -dx11",
            "%command% --launcher-skip",
            "%command% +set r_mode 5",
            "%command% --profile game.",
            'SteamDeck=0 %command% --profile "game name"',
            "%command% --profile=game.",
            "SteamDeck=0 %command%",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(protondb._extract_launch_options(report(command)), [command])
                result = protondb._analyse_reports([report(command)], {})
                self.assertEqual(result["ranked_options"][0]["command"], command)

    def test_assignments_directly_after_wrappers_are_not_ranked(self):
        commands = (
            "FOO=1 gamemoderun FOO=2 %command%",
            "gamemoderun FOO=2 %command%",
            "env FOO=1 gamemoderun FOO=2 %command%",
            "SteamDeck=0 gamemoderun SteamDeck=1 %command%",
            "gamescope SteamDeck=0 %command%",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(protondb._extract_launch_options(report(command)), [])
                self.assertEqual(protondb._analyse_reports([report(command)], {})["ranked_options"], [])
        self.assertEqual(
            protondb._assignment_items(commands[0]), [("FOO", "1")]
        )
        self.assertNotEqual(
            protondb._command_semantics(commands[0])["family_key"],
            protondb._command_semantics("FOO=2 gamemoderun %command%")["family_key"],
        )

    def test_equivalent_environment_prefixes_share_counts(self):
        commands = (
            "FOO=2 gamemoderun %command%",
            "env FOO=2 gamemoderun %command%",
            'FOO=1 env FOO="2" gamemoderun %command%',
        )
        for command in commands:
            self.assertEqual(protondb._extract_launch_options(report(command)), [command])
            self.assertEqual(protondb._assignment_value(command, "FOO"), "2")
        result = protondb._analyse_reports([report(command) for command in commands], {})
        self.assertEqual(len(result["ranked_options"]), 1)
        self.assertEqual(result["ranked_options"][0]["count"], 3)

    def test_explicit_env_inside_wrapper_retains_its_scope(self):
        commands = (
            "FOO=1 gamemoderun env FOO=2 %command%",
            "FOO=2 gamemoderun %command%",
        )
        result = protondb._analyse_reports([report(command) for command in commands], {})
        self.assertEqual(len(result["ranked_options"]), 2)
        self.assertEqual([item["count"] for item in result["ranked_options"]], [1, 1])
        self.assertEqual(protondb._assignment_items(commands[0]), [("FOO", "1")])

    def test_pragmata_3357650_wine_detection_values_are_preserved_and_separate(self):
        commands = (
            "%command% /WineDetectionEnabled:False",
            "%command% /WineDetectionEnabled:True",
        )
        fixtures = [report(command) for command in commands]
        for item in fixtures:
            item["appid"] = 3357650
        with (
            patch.object(protondb, "detect_local_system_profile", return_value={"gpu_vendors": []}),
            patch.object(protondb, "_fetch_summary", return_value={"effective_tier": "gold", "total": 2}),
            patch.object(protondb, "_fetch_detailed_reports", return_value=(fixtures, 2, None)) as fetch,
        ):
            result = protondb.analyse_protondb(3357650)
        self.assertEqual(fetch.call_args.args, (3357650,))
        self.assertEqual(result["appid"], 3357650)
        self.assertEqual(result["reports_analysed"], 2)
        self.assertEqual({item["command"] for item in result["ranked_options"]}, set(commands))
        self.assertEqual([item["count"] for item in result["ranked_options"]], [1, 1])

    def test_slash_options_are_generic_and_combine_with_environment_and_flags(self):
        commands = (
            "SteamDeck=0 %command% /WineDetectionEnabled:False -dx11",
            'WINEDLLOVERRIDES="version=n,b;winmm=n,b" %command% /Render.Mode:RayTracing.',
            "env PROTON_NO_ESYNC=1 %command% --profile game. /FrameRate:60",
            "%command% /MixedCase_Name:VaLuE.,",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(protondb._extract_launch_options(report(command)), [command])
                self.assertEqual(protondb._normalise_command(command), command)
                self.assertTrue(protondb._is_safe_to_surface(command))
                ranked = protondb._analyse_reports([report(command)], {})["ranked_options"]
                self.assertEqual(ranked[0]["command"], command)
        invalid = ("%command% /WineDetectionEnabled:", "%command% /WineDetectionEnabled False")
        for command in invalid:
            with self.subTest(command=command):
                self.assertEqual(protondb._extract_launch_options(report(command)), [])


def response(payload=None, status=200, json_error=None):
    result = Mock(status_code=status)
    result.raise_for_status.side_effect = requests.HTTPError("HTTP 503") if status >= 400 else None
    result.json.return_value = payload
    result.json.side_effect = json_error
    return result


class ProtonDBNetworkTests(unittest.TestCase):
    def analyse(self, pages, max_pages=3):
        with (
            patch.object(protondb, "detect_local_system_profile", return_value={"gpu_vendors": []}),
            patch.object(protondb, "_fetch_summary", return_value={"effective_tier": "gold", "total": 2}),
            patch.object(protondb.requests, "get", side_effect=[response({"reports": 12, "timestamp": 34}), *pages]),
        ):
            return protondb.analyse_protondb(620, max_pages=max_pages)

    def page(self, command="SteamDeck=0 %command%"):
        return response({"reports": [report(command)], "total": 2, "perPage": 1})

    def failures(self):
        return (
            ("HTTP 503", response(status=503)),
            ("invalid JSON", response(json_error=ValueError("Invalid JSON"))),
            ("timeout", requests.Timeout("Timeout")),
        )

    def test_later_page_failures_preserve_reports_and_mark_partial(self):
        for name, failure in self.failures():
            with self.subTest(failure=name):
                result = self.analyse([self.page(), failure])
                self.assertEqual(result["reports_analysed"], 1)
                self.assertEqual(result["report_total"], 2)
                self.assertTrue(result["reports_partial"])
                self.assertTrue(result["detail_error"])
                self.assertEqual(result["ranked_options"][0]["command"], "SteamDeck=0 %command%")

    def test_first_page_failures_have_no_partial_results(self):
        for name, failure in self.failures():
            with self.subTest(failure=name):
                result = self.analyse([failure])
                self.assertEqual(result["reports_analysed"], 0)
                self.assertFalse(result["reports_partial"])
                self.assertTrue(result["detail_error"])
                self.assertEqual(result["ranked_options"], [])
                self.assertEqual(result["summary"]["effective_tier"], "gold")

    def test_successful_pages_are_not_marked_partial(self):
        result = self.analyse([self.page(), self.page()])
        self.assertEqual(result["reports_analysed"], 2)
        self.assertFalse(result["reports_partial"])
        self.assertIsNone(result["detail_error"])
        self.assertEqual(result["ranked_options"][0]["count"], 2)

    def test_first_page_404_falls_back_to_all_devices(self):
        result = self.analyse([response(status=404), self.page(), self.page()])
        self.assertEqual(result["reports_analysed"], 2)
        self.assertIsNone(result["detail_error"])

    def test_no_reports_summary_does_not_request_pages(self):
        with (
            patch.object(protondb, "detect_local_system_profile", return_value={}),
            patch.object(protondb.requests, "get", return_value=response(status=404)) as get,
        ):
            result = protondb.analyse_protondb(620)
        self.assertIsNone(result["summary"])
        self.assertEqual(result["reports_analysed"], 0)
        get.assert_called_once()

    def test_page_limit_is_kept(self):
        result = self.analyse([self.page()], max_pages=1)
        self.assertEqual(result["reports_analysed"], 1)
        self.assertIsNone(result["detail_error"])


if __name__ == "__main__":
    unittest.main()
