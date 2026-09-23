#
#	Makefile for the model-render-print project.
#
#	This Makefile is the human-facing driver.
#	Each rule calls the appropriate tool instead of reimplementing work:
#		build:  sh scripts/stl-tiles-build.sh (render the STL tile set)
#		        with --oceans-flat (flat oceans; see documents/05-stl-approach.md)
#		frame:  sh scripts/frame-build.sh (render the assembly-frame model)
#		rings:  sh scripts/rings-build.sh (render the support ring lattice)
#		step:   sh scripts/step-build.sh (export the tile set as STEP,
#		        in assembly, for CAD editing)
#		check:  sh scripts/stl-tiles-build.sh check (validate tiles)
#		site:   sh scripts/site-build.sh + sh scripts/site-condense.sh
#		        (the standard page set; see prompts/features/02-project-pages.md)
#		state:  sh scripts/site-state-fetch.sh (dataset + tile state)
#		clean:  rm generated output
#		test:   npm test
#		deploy: RETIRED - all publishing to labs.bannister.us goes through
#		        the homelab project (homelab-publish; see the homelab's
#		        documents/09-project-pages-conventions.md). This target
#		        only reminds you of that; use the homelab's make deploy.
#		install: reserved; not yet defined.
#

build:
	sh scripts/stl-tiles-build.sh build --oceans-flat

frame:
	sh scripts/frame-build.sh

rings:
	sh scripts/rings-build.sh --sample-degrees 1.0

step:
	sh scripts/step-build.sh --sample-degrees 5.0

check:
	sh scripts/stl-tiles-build.sh check

site:
	sh scripts/site-build.sh
	sh scripts/site-condense.sh

state:
	sh scripts/site-state-fetch.sh

clean:
	rm -f dataflow.out/* site.out/* logs/*

test:
	npm test

deploy:
	@echo '==== RETIRED: publishing goes through the homelab project (homelab-publish).'
	@echo '==== Build the pages here (make site / make state), then run the homelab''s'
	@echo '==== "make deploy" to publish (see homelab documents/09-project-pages-conventions.md).'

install:
	@echo '==== No install yet defined'

.PHONY: build frame rings step check site state clean test deploy install
