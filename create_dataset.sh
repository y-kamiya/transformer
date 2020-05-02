#!/bin/bash

data_dir=$1
src=${2:-en}
tgt=${3:-fr}
vocab_size=${4:-1000}
valid_count=${5:-0}
max_words=${6:-1000000}

script_dir=$(cd `dirname $0`; pwd)
model_prefix=spm

pushd $data_dir

function encode()
{
    local lang=$1
    local data_type=$2
    local model_prefix=$3

    cat $data_type.orig.$lang \
        | $script_dir/sentencepiece/build/src/spm_encode --model=$model_prefix.model --output_format=id \
        | sed -e 's/^/1 /' -e 's/$/ 2/' \
        > $data_type.$lang
}

function remove_long_sentences()
{
    local input_src=$1
    local input_tgt=$2
    local max_words=$3

    cat $input_src | awk  -v mw=$max_words 'mw < NF || NF <= 2 { print NR "d" }' > a.tmp
    cat $input_tgt | awk  -v mw=$max_words 'mw < NF || NF <= 2 { print NR "d" }' >> a.tmp
    cat a.tmp | sort | uniq > b.tmp

    sed -f b.tmp $input_src > c.tmp
    sed -f b.tmp $input_tgt > d.tmp

    mv c.tmp $input_src
    mv d.tmp $input_tgt

    rm *.tmp
}

function separate()
{
    local lang=$1
    local valid_count=$2

    # separate data for train and valid
    head -n $valid_count train.$lang > valid.$lang
    sed -e "1,${valid_count}d" train.$lang > a.tmp

    # use tmp file to avoid using 'sed -i' because usage is different between GNU and BSD
    mv a.tmp train.$lang
}

cat train.orig.$src train.orig.$tgt > spm_input
$script_dir/sentencepiece/build/src/spm_train --input=spm_input --model_prefix=$model_prefix --vocab_size=$vocab_size --pad_id=3

function build()
{
    local data_type=$1
    encode $src $data_type $model_prefix
    encode $tgt $data_type $model_prefix

    remove_long_sentences $data_type.$src $data_type.$tgt $max_words
}

build train

if [ -f valid.orig.$src ]; then
    build valid
fi
if [ -f test.orig.$src ]; then
    build test
fi

# separate valid data from train data
if [ $valid_count != 0 ]; then
    separate $src $valid_count
    separate $tgt $valid_count
fi

popd

