# help.mk version 2.3 (2025-11-29)
#
# Helpful Makefile rules for 'make help'
# https://github.com/mgedmin/python-project-skel

# Tweaking the look of 'make help'; most of these are awk literals and need the quotes
HELP_INDENT = ""
HELP_PREFIX = "make "
HELP_WIDTH = 24
HELP_SEPARATOR = " \# "
HELP_SECTION_SEP = "\n"
HELP_SAME_AS = "same as '\033[36mmake %s\033[0m'"

.PHONY: help
help:
	@grep -Eh -e '^[a-zA-Z0-9_ -]+:.*?##: .*$$' -e '^ *##:' $(MAKEFILE_LIST) \
	    | awk 'BEGIN {FS = "(^|:[^#]*|^ +)##: "; section=""}; \
	          /^##:$$/ {printf "%s", section; section=$(HELP_SECTION_SEP)} \
	          /^##:./ {printf "%s%s\n%s", section, $$2, $(HELP_SECTION_SEP); section=$(HELP_SECTION_SEP)} \
	          /^ +##:./ {printf "%s%-$(HELP_WIDTH)s%s%s\n", $(HELP_INDENT), "", $(HELP_SEPARATOR), $$2; section=$(HELP_SECTION_SEP)} \
	          /^[^#]/ {split($$1, targets, " "); desc=$$2; \
	                   for (i in targets) { \
	                     printf "%s\033[36m%-$(HELP_WIDTH)s\033[0m%s%s\n", $(HELP_INDENT), $(HELP_PREFIX) targets[i], $(HELP_SEPARATOR), desc; \
	                     desc=sprintf($(subst ','"'"',$(HELP_SAME_AS)), targets[1]); \
	                   } \
	                   section=$(HELP_SECTION_SEP)}'
