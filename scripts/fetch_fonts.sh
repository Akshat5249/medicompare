#!/usr/bin/env bash
# Downloads open-licensed (SIL OFL) handwriting fonts from the Google Fonts repository.
set -euo pipefail
cd "$(dirname "$0")/../evaluation/fonts"
base="https://raw.githubusercontent.com/google/fonts/main/ofl"
fetch() { curl --fail --silent --show-error --location --max-time 60 --output "$2" "$base/$1"; echo "fetched $2"; }
fetch "caveat/Caveat%5Bwght%5D.ttf" Caveat.ttf
fetch "kalam/Kalam-Regular.ttf" Kalam-Regular.ttf
fetch "shadowsintolight/ShadowsIntoLight.ttf" ShadowsIntoLight.ttf
fetch "reeniebeanie/ReenieBeanie.ttf" ReenieBeanie.ttf
fetch "indieflower/IndieFlower-Regular.ttf" IndieFlower-Regular.ttf
fetch "handlee/Handlee-Regular.ttf" Handlee-Regular.ttf
fetch "nothingyoucoulddo/NothingYouCouldDo.ttf" NothingYouCouldDo.ttf
fetch "gochihand/GochiHand-Regular.ttf" GochiHand-Regular.ttf
