#!/usr/bin/env python3
"""
episode_formatter.py - Episode list formatter

Convert episode lists pasted from Wikipedia / IMDb / TheTVDB / plain text into
the CSV format Scene Segment Splitter expects:

    SeasonNumber,EpisodeNumber,EpisodeName,AbbvCombo

Use standalone (`python episode_formatter.py`) or via the GUI's Episode Manager.
"""

import re
import csv
import sys
from io import StringIO
from typing import List, Dict, Optional


class EpisodeFormatter:
    def __init__(self):
        # (regex, type). Order matters: more specific patterns first.
        self.patterns = [
            # S01E01 - Title / 1x01 - Title / S01E01: Title / S01E01 Title
            (r'^[Ss]?(\d{1,2})[xXeE](\d{1,3})\s*(?:[-–—:]\s*|\s+)(.+)$', 'standard'),
            # S1.E1 . Title  (IMDb)
            (r'^S(\d{1,2})\.E(\d{1,3})\s*[∙·:\-–—]\s*(.+)$', 'imdb'),
            # Season 1, Episode 1: Title
            (r'^Season\s*(\d{1,2}),?\s*Episode\s*(\d{1,3})\s*[:\-–—]?\s*(.+)$', 'verbose'),
            # "Title" (S1E1) / (1x01)
            (r'^["\'](.+?)["\']\s*\([Ss]?(\d{1,2})[xXeE](\d{1,3})\)$', 'quoted'),
            # Title (1.01)  -> season.episode
            (r'^(.+?)\s*\((\d{1,2})\.(\d{2})\)$', 'title_first'),
            # 1.01 Title  -> season.episode
            (r'^(\d{1,2})\.(\d{2})\s+(.+)$', 'dotted_se'),
            # 1. Title  (numbered; uses default season)
            (r'^(\d{1,3})\.\s*(.+)$', 'numbered'),
            # Episode 1: Title  (uses default season)
            (r'^Episode\s*(\d{1,3})\s*[:\-–—]?\s*(.+)$', 'episode_only'),
            # 1 "Title"  (Wikipedia; uses default season)
            (r'^(\d{1,3})\s+["\'](.+?)["\']', 'wiki_quoted'),
            # 1 Title  (bare number then title; uses default season) - last resort
            (r'^(\d{1,3})\s+(.+)$', 'numbered_space'),
        ]

    def parse_episode_list(self, text: str, default_season: int = 1) -> List[Dict]:
        episodes: List[Dict] = []
        current_season = default_season
        for raw in text.strip().split('\n'):
            line = raw.strip()
            if not line:
                continue
            # A standalone "Season N" header sets the running season.
            header = re.match(r'^Season\s*(\d{1,2})\s*:?\s*$', line, re.IGNORECASE)
            if header:
                current_season = int(header.group(1))
                continue
            try:
                info = self.parse_episode_line(line, current_season)
            except Exception:
                info = None
            if info:
                episodes.append(info)
        return episodes

    def parse_episode_line(self, line: str, default_season: int = 1) -> Optional[Dict]:
        line = re.sub(r'\s+', ' ', line.strip())
        if not line:
            return None

        for pattern, kind in self.patterns:
            m = re.match(pattern, line)
            if not m:
                continue
            if kind in ('standard', 'imdb', 'verbose'):
                return {'season': int(m.group(1)), 'episode': int(m.group(2)),
                        'title': self.clean_title(m.group(3))}
            if kind == 'quoted':
                return {'season': int(m.group(2)), 'episode': int(m.group(3)),
                        'title': self.clean_title(m.group(1))}
            if kind in ('title_first',):
                return {'season': int(m.group(2)), 'episode': int(m.group(3)),
                        'title': self.clean_title(m.group(1))}
            if kind == 'dotted_se':
                return {'season': int(m.group(1)), 'episode': int(m.group(2)),
                        'title': self.clean_title(m.group(3))}
            if kind in ('numbered', 'episode_only', 'wiki_quoted', 'numbered_space'):
                return {'season': default_season, 'episode': int(m.group(1)),
                        'title': self.clean_title(m.group(2))}
        return None

    def clean_title(self, title: str) -> str:
        title = title.strip()
        # Strip a *matched* surrounding quote pair only (keeps "'Tis the Season").
        if len(title) >= 2 and title[0] == title[-1] and title[0] in '"\'':
            title = title[1:-1].strip()
        # Remove ISO dates and clearly-delimited air dates.
        title = re.sub(r'\s*\(\d{4}-\d{2}-\d{2}\)\s*$', '', title)
        title = re.sub(
            r'\s*\d{1,2}\s+(January|February|March|April|May|June|July|August|'
            r'September|October|November|December)\s+\d{4}\s*$', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\s*\(aired.*?\)\s*$', '', title, flags=re.IGNORECASE)
        return ' '.join(title.split())

    def generate_csv(self, episodes: List[Dict], output_file: Optional[str] = None) -> str:
        buf = StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator='\n')
        writer.writerow(["SeasonNumber", "EpisodeNumber", "EpisodeName", "AbbvCombo"])
        for ep in episodes:
            writer.writerow([ep['season'], ep['episode'], ep['title'],
                             f"S{ep['season']:02d}E{ep['episode']:02d}"])
        content = buf.getvalue().rstrip('\n')
        if output_file:
            with open(output_file, 'w', encoding='utf-8', newline='') as f:
                f.write(content + '\n')
        return content


def main():
    print("Episode List Formatter")
    print("=" * 50)
    print("\nPaste your episode list below. Enter a blank line when done:")
    lines = []
    while True:
        try:
            line = input()
            if line.strip() == "" and lines:
                break
            lines.append(line)
        except EOFError:
            break
    if not lines:
        print("No input provided.")
        return

    default_season = input("\nDefault season number (press Enter for 1): ").strip()
    default_season = int(default_season) if default_season.isdigit() else 1

    formatter = EpisodeFormatter()
    episodes = formatter.parse_episode_list('\n'.join(lines), default_season)
    if not episodes:
        print("\nNo episodes could be parsed. Please check the format.")
        return

    print(f"\nParsed {len(episodes)} episodes:")
    for ep in episodes[:5]:
        print(f"  S{ep['season']:02d}E{ep['episode']:02d} - {ep['title']}")
    if len(episodes) > 5:
        print(f"  ... and {len(episodes) - 5} more")

    if input("\nSave to CSV file? (y/n): ").strip().lower() == 'y':
        filename = input("Filename (default: episode_list.csv): ").strip() or "episode_list.csv"
        formatter.generate_csv(episodes, filename)
        print(f"\nSaved to {filename}")
    else:
        print("\nCSV Output:\n" + "-" * 50)
        print(formatter.generate_csv(episodes))


if __name__ == "__main__":
    main()
