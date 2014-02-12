#!/usr/bin/python
"""
Generate a summary for all my projects.
"""

import glob
import os
import subprocess
import argparse


__author__ = 'Marius Gedminas <marius@gedmin.as>'
__version__ = '0.1'


#
# Configuration
#

REPOS = '/var/lib/jenkins/jobs/*/workspace'


#
# Utilities
#

def pipe(*cmd, **kwargs):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, **kwargs)
    return p.communicate()[0]


#
# Data extraction
#

def get_repos():
    return sorted(dirname for dirname in glob.glob(REPOS)
                  if os.path.isdir(os.path.join(dirname, '.git')))


def get_repo_url(repo_path):
    return pipe("git", "remote", "-v", cwd=repo_path).splitlines()[0].split()[1]


def normalize_github_url(url):
    if not url.startswith('https://github.com/'):
        return url
    if url.endswith('.git'):
        url = url[:-len('.git')]
    return url


def get_project_name(url):
    return url.rpartition('/')[-1]


def get_last_tag(repo_path):
    return pipe("git", "describe", "--tags", "--abbrev=0",
                cwd=repo_path).strip()


def get_date_of_tag(repo_path, tag):
    return pipe("git", "log", "-1", "--format=%ai", tag, cwd=repo_path).strip()


def get_pending_commits(repo_path, last_tag):
    return pipe("git", "log", "--oneline", "{}..origin/master".format(last_tag),
                cwd=repo_path).splitlines()


class Project(object):

    def __init__(self, working_tree, url, last_tag, last_tag_date,
                 pending_commits):
        self.working_tree = working_tree
        self.url = url
        self.last_tag = last_tag
        self.last_tag_date = last_tag_date
        self.pending_commits = pending_commits

    @classmethod
    def from_working_tree(cls, working_tree):
        url = normalize_github_url(get_repo_url(working_tree))
        last_tag = get_last_tag(working_tree)
        last_tag_date = get_date_of_tag(working_tree, last_tag)
        pending_commits = get_pending_commits(working_tree, last_tag)
        return cls(working_tree, url, last_tag, last_tag_date, pending_commits)

    @property
    def name(self):
        return get_project_name(self.url)

    @property
    def compare_url(self):
        return '{base}/compare/{tag}...master'.format(base=self.url,
                                                      tag=self.last_tag)


def get_projects():
    for path in get_repos():
        yield Project.from_working_tree(path)


def main():
    parser = argparse.ArgumentParser(
            description="Summarize release status of projects in %s" % REPOS)
    parser.add_argument('--version', action='version',
                        version="%(prog)s version " + __version__)
    parser.add_argument('-v', '--verbose', action='count',
                        help='be more verbose (can be repeated)')
    args = parser.parse_args()
    for project in get_projects():
        print("{name:20} {commits:4} commits since {release:6} ({date})".format(
            name=project.name, commits=len(project.pending_commits),
            release=project.last_tag, date=project.last_tag_date))
        if args.verbose:
            print("  {}".format(project.compare_url))
            if args.verbose > 1:
                print("  {}".format(project.working_tree))
            print("")


if __name__ == '__main__':
    main()
