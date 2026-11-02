#!/bin/sh
# ============================================================================
# 00_download.sh -- the files the project needs that nobody writes by hand
# ----------------------------------------------------------------------------
# usage: ./00_download.sh            (a file already in work/ is kept, not fetched again)
#
# makes: work/sentencepiece.bpe.model   XLM-R's tokenizer model (5 MB, MIT, from Hugging Face)
#        work/xlm-stats.dqt             the centering statistics, 153 KB: tensors `mean` [1,1024]
#                                       and `whiten` [256,1024], fitted once on 1 616 sentences in
#                                       several languages, as raw integers at the scale
#                                       02_xlm_classify.mnd and 02_label_embed.mnd use
#        work/xlmr-large.int32.dqt      the model as exact integers (1.85 GB; only needed
#                                       by 00_provision.mnd, once per worker)
# Every download is checked against its published sha256 before it is kept.
# ============================================================================
. "$(dirname "$0")/_common.sh"

HF=https://huggingface.co/FacebookAI/xlm-roberta-large/resolve/main
REL=https://github.com/FabianoDicheti/maned/releases/latest/download

fetch() {   # fetch NAME URL SHA256
  if [ -f "work/$1" ]; then echo "work/$1: kept"; return; fi
  echo "work/$1: downloading"
  curl -fsSL -o "work/$1.part" "$2"
  got=$(shasum -a 256 "work/$1.part" | cut -c1-64)
  [ "$got" = "$3" ] || { echo "error: work/$1 sha256 $got, expected $3 - not kept" >&2; rm -f "work/$1.part"; exit 1; }
  mv "work/$1.part" "work/$1"
}

fetch sentencepiece.bpe.model "$HF/sentencepiece.bpe.model" cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865
fetch xlm-stats.dqt           "$REL/xlm-stats.dqt"           9a20130ca72b7ecacaf4cb71d3ead4ccbff654dc7779d77643e35723e02ca6ef
if [ "${WITH_WEIGHTS:-0}" = 1 ]; then
  fetch xlmr-large.int32.dqt  "$REL/xlmr-large.int32.dqt"    d84e81a8da7b8898713d3a4861091c1961210a82b71f5fa99b9f8730ad5d9dd7
else
  echo "work/xlmr-large.int32.dqt: skipped (WITH_WEIGHTS=1 fetches it; only 00_provision.mnd needs it)"
fi
echo "download done"
