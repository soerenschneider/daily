#!/usr/bin/env python3

import argparse
import os.path
import re
import subprocess
import sys

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, List

DEFAULT_EDITOR = 'vim'
ENTRIES_DIR = "~/Work/daily"
DEFAULT_EXTENSION = "txt"
DATE_FORMAT = "%Y-%m-%d"

daily_entry_regex = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class IllegalDateException(Exception):
    pass


@dataclass
class Result:
    items: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    daily_date: str = ""


class Daily:
    def __init__(self, driver):
        self.driver = driver

    @staticmethod
    def _validate_date(daily_date: str) -> None:
        if not daily_date:
            raise IllegalDateException("empty date given")

        if not daily_entry_regex.match(daily_date.strip()):
            raise IllegalDateException(f"Invalid date {daily_date}, "
                                       f"date must be in format {DATE_FORMAT}")

    @staticmethod
    def compute_date(days_offset=0) -> str:
        computed_date = date.today() + timedelta(days_offset)
        return computed_date.strftime(DATE_FORMAT)

    def translate_date(self, special_date: str) -> str:
        special_date = special_date.lower().strip()
        if special_date in ["today", "t"]:
            return Daily.compute_date(days_offset=0)
        if special_date in ["yesterday", "y"]:
            return Daily.compute_date(days_offset=-1)
        if special_date in ["last", "l"]:
            return self.get_latest_entry()

        Daily._validate_date(special_date)
        return special_date

    def has_entry(self, daily_date) -> bool:
        return self.driver.has_entry(daily_date)

    def get_latest_entry(self) -> Optional[str]:
        for i in range(30):
            daily_date = Daily.compute_date(-i)
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

            result.warnings.append(f"Nothing found for {daily_date}, "
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
        return os.path.join(self._daily_entries_dir, f"{daily_date}.{DEFAULT_EXTENSION.lstrip('.')}")

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
            subprocess.call([DEFAULT_EDITOR, filename])
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


class BColors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument("-d", '--date', type=str, help="specify a date the command applies to",
                        default="today", action="store")
    subparsers = parser.add_subparsers(dest="command")

    parser_add = subparsers.add_parser('add', help='add one or more entries for a given day')
    parser_add.add_argument("-m", help='express the work item', dest="message",
                            nargs="+", action="append")

    subparsers.add_parser('get', help='read entries for a given day')
    subparsers.add_parser('edit', help='edit entries for a given day')
    subparsers.add_parser('nuke', help='delete entries for a given day')

    return parser.parse_args()


def confirm_deletion(prompt: str) -> bool:
    print(f"{BColors.WARNING}{prompt}{BColors.ENDC}")
    choice = input().lower()
    return choice in {'yes', 'y'}


def render_output(result: Result) -> None:
    if result.warnings:
        for warning in result.warnings:
            print(f"{BColors.WARNING}{warning}")
        print(BColors.ENDC)

    for i in result.items:
        print(f"- {i}", end="")


def main():
    arg = parse_args()

    driver = FsDriver()
    daily = Daily(driver)

    parsed_date = None
    try:
        parsed_date = daily.translate_date(arg.date)
    except IllegalDateException as err:
        print(f"{BColors.FAIL}{err}{BColors.ENDC}")
        sys.exit(1)

    if arg.command == "add":
        for messages in arg.message:
            daily.add_entry(parsed_date, " ".join(messages))
    elif arg.command == "edit":
        result = daily.edit_entry(parsed_date)
        render_output(result)
    elif arg.command == "nuke":
        daily.get_entry(parsed_date)
        confirm_deletion(f"Do you want to delete all entries for {parsed_date}? y/N")
        daily.nuke_entries(parsed_date)
    else:
        result = daily.get_entry(parsed_date)
        render_output(result)


if __name__ == '__main__':
    main()
