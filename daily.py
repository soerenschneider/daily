#!/usr/bin/env python3

import os.path
import argparse
import re
import subprocess
import sys

from typing import Optional, List
from pathlib import Path
from datetime import date, timedelta


ENTRIES_DIR = "~/Work/daily"
DEFAULT_EXTENSION = "txt"
DATE_FORMAT = "%Y-%m-%d"

daily_entry_regex = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class IllegalDateException(Exception):
    pass


class Result:
    def __init__(self):
        self.items = list()
        self.warnings = list()
        self.daily_date = None


class Daily:
    def __init__(self, driver):
        self.driver = driver

    @staticmethod
    def _validate_date(daily_date: str) -> None:
        if not daily_date:
            raise IllegalDateException()

        if not daily_entry_regex.match(daily_date):
            raise IllegalDateException()

    @staticmethod
    def get_date(days=0) -> str:
        computed_date = date.today() + timedelta(days)
        return computed_date.strftime(DATE_FORMAT)

    @staticmethod
    def translate_date(special_date: str) -> str:
        special_date = special_date.lower()
        if special_date in ["today", "t"]:
            return Daily.get_date(0)
        if special_date in ["yesterday", "y"]:
            return Daily.get_date(-1)

        Daily._validate_date(special_date)
        return special_date

    def has_entry(self, daily_date) -> bool:
        return self.driver.has_entry(daily_date)

    def get_latest_entry(self) -> Optional[str]:
        for i in range(30):
            daily_date = Daily.get_date(-i)
            if self.has_entry(daily_date):
                return daily_date
        return None

    def get_entry(self, daily_date: str) -> Optional[Result]:
        result = Result()
        if not self.has_entry(daily_date):
            new_daily_date = self.get_latest_entry()
            if not new_daily_date:
                result.warnings.append("No entries found for the last 30 days")
                return result

            result.warnings.append(f"Nothing found for {daily_date},"
                                   f"showing results for {new_daily_date}")
            daily_date = new_daily_date

        result.items = self.driver.get_entry(daily_date)
        result.daily_date = daily_date
        return result

    def nuke_entries(self, daily_date: str) -> bool:
        return self.driver.nuke_entries(daily_date)

    def edit_entry(self, daily_date: str) -> Result:
        return self.driver.edit_entry(daily_date)

    def add_entry(self, daily_date: str, content: str) -> None:
        return self.driver.add_entry(daily_date, content)


class FsDriver:
    def __init__(self, daily_entries_dir=ENTRIES_DIR):
        self._daily_entries_dir = os.path.expanduser(daily_entries_dir)
        self._sanitize()

    def _sanitize(self):
        daily_db_dir = Path(self._daily_entries_dir)
        if not daily_db_dir.is_dir():
            print(f"Creating dir {self._daily_entries_dir}")
            daily_db_dir.mkdir(parents=True)

    def _get_filename(self, daily_date: str) -> str:
        return os.path.join(self._daily_entries_dir, f"{daily_date}.{DEFAULT_EXTENSION}")

    def has_entry(self, daily_date) -> bool:
        filename = self._get_filename(daily_date)
        file_path = Path(filename)
        return file_path.exists()

    def nuke_entries(self, daily_date: str) -> bool:
        if self.has_entry(daily_date):
            filename = self._get_filename(daily_date)
            os.remove(filename)
            return True
        return False

    def edit_entry(self, daily_date: str) -> Result:
        result = Result()
        if not self.has_entry(daily_date):
            result.warnings.append(f"No entry for {daily_date}")
        else:
            filename = self._get_filename(daily_date)
            subprocess.call(['vim', filename])
            # check if we deleted all lines
            if os.stat(filename).st_size == 0:
                self.nuke_entries(daily_date)
                result.warnings.append(f"Deleted entries file {daily_date} because it was empty")
        return result

    def get_entry(self, daily_date: str) -> List[str]:
        if not self.has_entry(daily_date):
            return []

        filename = self._get_filename(daily_date)
        with open(filename, 'r') as content:
            return content.readlines()

    def add_entry(self, daily_date: str, content: str) -> None:
        mode = "a"
        if not self.has_entry(daily_date):
            mode = "w"

        filename = self._get_filename(daily_date)
        with open(filename, mode) as entries_file:
            entries_file.write(content + os.linesep)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument("-d", '--date', type=str, default="today", action="store")
    subparsers = parser.add_subparsers(help='help for subcommand', dest="command")

    parser_add = subparsers.add_parser('add', help='add entries to a given day')
    parser_add.add_argument("-m", dest="message", nargs="+", action="append")

    subparsers.add_parser('get', help='read entry for a given day')
    subparsers.add_parser('edit', help='delete a single entry for a given day')
    subparsers.add_parser('nuke', help='delete all entries for a given day')

    return parser.parse_args()


def confirm_deletion(prompt: str) -> bool:
    print(prompt)
    choice = input().lower()
    if choice in {'yes', 'y'}:
        return True
    return False


def render_output(result: Result) -> None:
    if result.warnings:
        for warning in result.warnings:
            print(warning)
        print()

    for i in result.items:
        print(f"- {i}", end="")


def main():
    arg = parse_args()
    daily_date = None
    try:
        daily_date = Daily.translate_date(arg.date)
    except IllegalDateException:
        print(f"Invalid date {daily_date}")
        sys.exit(1)

    driver = FsDriver()
    daily = Daily(driver)

    if arg.command == "add":
        for messages in arg.message:
            daily.add_entry(daily_date, " ".join(messages))
    elif arg.command == "edit":
        result = daily.edit_entry(daily_date)
        render_output(result)
    elif arg.command == "nuke":
        daily.get_entry(daily_date)
        confirm_deletion(f"Do you want to delete all entries for {daily_date}? y/N")
        daily.nuke_entries(daily_date)
    else:
        result = daily.get_entry(daily_date)
        render_output(result)


if __name__ == '__main__':
    main()
