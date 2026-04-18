#!/usr/bin/env python3
"""Harness for the playback chapter auto-detection flow.

This runs SkipIntroPlayer._try_autodetect() with Kodi modules mocked out. It is
meant to explain whether playback auto-detection fails because chapter names are
missing/generic, because patterns do not match, or because timestamps are absent
and chapter-seek mode is needed.
"""

import argparse
import importlib
import json
import os
import sys
import types


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeDatabase:
    def __init__(self):
        self.saved_config = None

    def get_show(self, title):
        return 1 if title else None

    def save_show_config(self, show_id, config):
        self.saved_config = dict(config)
        return True

    def close(self):
        pass


def install_kodi_mocks():
    logs = []

    class Player:
        def isPlaying(self):
            return True

        def isPlayingVideo(self):
            return True

        def getPlayingFile(self):
            return '/fixtures/Harness.Show.S01E01.mkv'

    class Monitor:
        pass

    xbmc = types.SimpleNamespace(
        LOGDEBUG=0,
        LOGINFO=1,
        LOGERROR=2,
        LOGWARNING=3,
        Player=Player,
        Monitor=Monitor,
        log=lambda msg, level=1: logs.append({'level': level, 'message': msg}),
        sleep=lambda ms: None,
        executebuiltin=lambda cmd: None,
        executeJSONRPC=lambda payload: json.dumps({
            'result': {'item': {'file': '/fixtures/Harness.Show.S01E01.mkv'}}
        }),
        getInfoLabel=lambda label: {
            'VideoPlayer.TVShowTitle': 'Harness Show',
            'VideoPlayer.Season': '1',
            'VideoPlayer.Episode': '1',
            'Player.Chapter': '1',
            'Player.ChapterCount': '3',
        }.get(label, ''),
    )

    xbmcgui = types.SimpleNamespace(
        NOTIFICATION_INFO='info',
        NOTIFICATION_ERROR='error',
        NOTIFICATION_WARNING='warning',
        ACTION_PREVIOUS_MENU=10,
        ACTION_NAV_BACK=92,
        Dialog=lambda: types.SimpleNamespace(
            yesno=lambda *args, **kwargs: True,
            notification=lambda *args, **kwargs: None,
        ),
        WindowXMLDialog=object,
    )

    class Addon:
        def getSetting(self, key):
            return {
                'enable_autoskip': 'true',
                'pre_skip_seconds': '3',
                'delay_autoskip': '0',
                'auto_dismiss_button': '0',
                'database_path': ':memory:',
                'backup_restore_path': '',
            }.get(key, '')

        def getSettingBool(self, key):
            return self.getSetting(key).lower() == 'true'

        def getAddonInfo(self, key):
            return REPO_ROOT if key == 'path' else ''

    xbmcaddon = types.SimpleNamespace(Addon=lambda addon_id=None: Addon())

    class File:
        def __init__(self, path, mode='r'):
            self.path = path

        def close(self):
            pass

        def size(self):
            return 0

    xbmcvfs = types.SimpleNamespace(
        translatePath=lambda path: path,
        exists=os.path.exists,
        mkdirs=lambda path: os.makedirs(path, exist_ok=True),
        File=File,
    )

    sys.modules['xbmc'] = xbmc
    sys.modules['xbmcgui'] = xbmcgui
    sys.modules['xbmcaddon'] = xbmcaddon
    sys.modules['xbmcvfs'] = xbmcvfs
    return logs


SCENARIOS = {
    'named-timestamps': {
        'chapters': [
            {'name': 'Cold Open', 'time': 0, 'number': 1},
            {'name': 'NCOP1', 'time': 42, 'number': 2},
            {'name': 'Part A', 'time': 92, 'number': 3},
            {'name': 'NCED', 'time': 1380, 'number': 4},
        ],
        'expect': {
            'intro_start': 42,
            'intro_bookmark': 92,
            'outro_bookmark': 1380,
            'skip_to_chapter': None,
            'saved': True,
        },
    },
    'named-no-timestamps': {
        'chapters': [
            {'name': 'Chapter 1', 'number': 1},
            {'name': 'OP1', 'number': 2},
            {'name': 'Episode Start', 'number': 3},
        ],
        'expect': {
            'intro_start': 0,
            'intro_bookmark': 99999,
            'outro_bookmark': None,
            'skip_to_chapter': 3,
            'saved': True,
        },
    },
    'generic-count-only': {
        'chapters': [
            {'name': 'Chapter 1', 'number': 1},
            {'name': 'Chapter 2', 'number': 2},
            {'name': 'Chapter 3', 'number': 3},
        ],
        'expect': {
            'intro_start': None,
            'intro_bookmark': None,
            'outro_bookmark': None,
            'skip_to_chapter': None,
            'saved': False,
        },
    },
}


def run_scenario(name, chapters, expect):
    logs = install_kodi_mocks()
    sys.path.insert(0, REPO_ROOT)

    for module_name in ('resources.lib.chapters', 'default'):
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
    import default

    db = FakeDatabase()
    default.get_database = lambda: None
    default.PlayerUI = lambda: types.SimpleNamespace(cleanup=lambda: None, close_dialog=lambda: None)
    player = default.SkipIntroPlayer()
    player.db = db
    player.show_info = {'title': 'Harness Show', 'season': 1, 'episode': 1}
    player.getChapters = lambda: chapters
    player._try_autodetect()

    actual = {
        'intro_start': player.intro_start,
        'intro_bookmark': player.intro_bookmark,
        'outro_bookmark': player.outro_bookmark,
        'skip_to_chapter': player._skip_to_chapter,
        'saved': db.saved_config is not None,
        'saved_config': db.saved_config,
    }
    passed = all(actual[key] == expected for key, expected in expect.items())
    return {
        'scenario': name,
        'passed': passed,
        'chapters': chapters,
        'expect': expect,
        'actual': actual,
        'logs': logs,
    }


def parse_args(argv):
    parser = argparse.ArgumentParser(description='Run SkipIntro chapter autodetect harness')
    parser.add_argument(
        '--scenario',
        choices=sorted(SCENARIOS) + ['all'],
        default='all',
        help='Scenario to run',
    )
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    names = sorted(SCENARIOS) if args.scenario == 'all' else [args.scenario]
    results = [
        run_scenario(name, SCENARIOS[name]['chapters'], SCENARIOS[name]['expect'])
        for name in names
    ]
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0 if all(result['passed'] for result in results) else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
