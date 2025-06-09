#!/usr/bin/env python3
"""
episode_formatter.py - Standalone Episode List Formatter

This tool helps convert episode lists from various formats into the CSV format
required by Scene Segment Splitter. It can parse lists from:
- Wikipedia
- IMDb
- TheTVDB
- TV Guide websites
- Plain text lists

Usage: python episode_formatter.py
Or paste directly into the Episode Manager tab in the GUI
"""

import re
import csv
import sys
from typing import List, Dict, Optional

class EpisodeFormatter:
    def __init__(self):
        self.patterns = [
            # S01E01 - Title or 1x01 - Title
            (r'[Ss]?(\d+)[xXeE](\d+)\s*[-–—]\s*(.+)', 'standard'),
            
            # Season 1, Episode 1: Title
            (r'Season\s*(\d+),?\s*Episode\s*(\d+):?\s*(.+)', 'verbose'),
            
            # "Title" (S1E1) or (1x01)
            (r'["\'](.+?)["\']\s*\([Ss]?(\d+)[xXeE](\d+)\)', 'quoted'),
            
            # 1. Title (needs season)
            (r'^(\d+)\.\s*(.+)', 'numbered'),
            
            # Episode 1: Title (needs season)
            (r'Episode\s*(\d+):?\s*(.+)', 'episode_only'),
            
            # Wikipedia format: 1 "Title" or 1 "Title" Date
            (r'^(\d+)\s*["\'](.+?)["\']\s*(?:\d{4}-\d{2}-\d{2})?', 'wiki_numbered'),
            
            # IMDb format: S1.E1 ∙ Title
            (r'S(\d+)\.E(\d+)\s*[∙·]\s*(.+)', 'imdb'),
            
            # Title (1.01) or Title (101)
            (r'(.+?)\s*\((\d)\.?(\d{2})\)', 'title_first'),
        ]
        
    def parse_episode_list(self, text: str, default_season: int = 1) -> List[Dict[str, any]]:
        """Parse episode list from text"""
        episodes = []
        lines = text.strip().split('\n')
        current_season = default_season
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Check for season headers
            season_match = re.match(r'Season\s*(\d+)', line, re.IGNORECASE)
            if season_match:
                current_season = int(season_match.group(1))
                continue
                
            # Try to parse episode
            episode_info = self.parse_episode_line(line, current_season)
            if episode_info:
                episodes.append(episode_info)
                
        return episodes
        
    def parse_episode_line(self, line: str, default_season: int = 1) -> Optional[Dict[str, any]]:
        """Parse a single episode line"""
        # Clean up common formatting
        line = line.strip()
        line = re.sub(r'\s+', ' ', line)  # Multiple spaces to single
        line = re.sub(r'^\d+\s+', '', line) if line[0].isdigit() and line[1] == ' ' else line  # Remove leading episode number without dot
        
        for pattern, pattern_type in self.patterns:
            match = re.match(pattern, line)
            if match:
                if pattern_type == 'standard':
                    return {
                        'season': int(match.group(1)),
                        'episode': int(match.group(2)),
                        'title': self.clean_title(match.group(3))
                    }
                elif pattern_type == 'verbose':
                    return {
                        'season': int(match.group(1)),
                        'episode': int(match.group(2)),
                        'title': self.clean_title(match.group(3))
                    }
                elif pattern_type == 'quoted':
                    return {
                        'season': int(match.group(2)),
                        'episode': int(match.group(3)),
                        'title': self.clean_title(match.group(1))
                    }
                elif pattern_type == 'numbered':
                    return {
                        'season': default_season,
                        'episode': int(match.group(1)),
                        'title': self.clean_title(match.group(2))
                    }
                elif pattern_type == 'episode_only':
                    return {
                        'season': default_season,
                        'episode': int(match.group(1)),
                        'title': self.clean_title(match.group(2))
                    }
                elif pattern_type == 'wiki_numbered':
                    return {
                        'season': default_season,
                        'episode': int(match.group(1)),
                        'title': self.clean_title(match.group(2))
                    }
                elif pattern_type == 'imdb':
                    return {
                        'season': int(match.group(1)),
                        'episode': int(match.group(2)),
                        'title': self.clean_title(match.group(3))
                    }
                elif pattern_type == 'title_first':
                    return {
                        'season': int(match.group(2)),
                        'episode': int(match.group(3)),
                        'title': self.clean_title(match.group(1))
                    }
                    
        return None
        
    def clean_title(self, title: str) -> str:
        """Clean up episode title"""
        # Remove quotes
        title = title.strip('"\'')
        
        # Remove dates in various formats
        title = re.sub(r'\s*\(\d{4}-\d{2}-\d{2}\)', '', title)
        title = re.sub(r'\s*\d{1,2}\s+\w+\s+\d{4}$', '', title)
        
        # Remove air date indicators
        title = re.sub(r'\s*\(aired.*?\)', '', title, flags=re.IGNORECASE)
        
        # Clean up extra spaces
        title = ' '.join(title.split())
        
        return title.strip()
        
    def generate_csv(self, episodes: List[Dict[str, any]], output_file: Optional[str] = None) -> str:
        """Generate CSV content from episodes"""
        csv_lines = ["SeasonNumber,EpisodeNumber,EpisodeName,AbbvCombo"]
        
        for ep in episodes:
            abbv = f"S{ep['season']:02d}E{ep['episode']:02d}"
            # Escape commas in title
            title = ep['title'].replace('"', '""')
            if ',' in title:
                title = f'"{title}"'
            csv_lines.append(f"{ep['season']},{ep['episode']},{title},{abbv}")
            
        csv_content = '\n'.join(csv_lines)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(csv_content)
                
        return csv_content

def main():
    """Interactive mode for standalone use"""
    print("Episode List Formatter")
    print("=" * 50)
    print("\nPaste your episode list below. Enter a blank line when done:")
    print("(Tip: You can paste multi-line content)")
    
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
        
    text = '\n'.join(lines)
    
    # Ask for default season
    default_season = input("\nDefault season number (press Enter for 1): ").strip()
    default_season = int(default_season) if default_season.isdigit() else 1
    
    # Parse episodes
    formatter = EpisodeFormatter()
    episodes = formatter.parse_episode_list(text, default_season)
    
    if not episodes:
        print("\nNo episodes could be parsed. Please check the format.")
        return
        
    print(f"\nParsed {len(episodes)} episodes:")
    for ep in episodes[:5]:  # Show first 5
        print(f"  S{ep['season']:02d}E{ep['episode']:02d} - {ep['title']}")
    if len(episodes) > 5:
        print(f"  ... and {len(episodes) - 5} more")
        
    # Ask to save
    save = input("\nSave to CSV file? (y/n): ").strip().lower()
    if save == 'y':
        filename = input("Filename (default: episode_list.csv): ").strip()
        filename = filename or "episode_list.csv"
        
        csv_content = formatter.generate_csv(episodes, filename)
        print(f"\nSaved to {filename}")
    else:
        # Print CSV to console
        print("\nCSV Output:")
        print("-" * 50)
        print(formatter.generate_csv(episodes))

if __name__ == "__main__":
    main()