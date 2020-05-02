#!/bin/bash

name=$1
src=${2:-en}
tgt=${3:-fr}
vocab_size=${4:-1000}
valid_count=${5:-1000}
max_words=${6:-1000000}

script_dir=$(cd `dirname $0`; pwd)
data_dir=$script_dir/data/$name

function encode()
{
    lang=$1
    data_dir=$2
    name=$3

    cat $data_dir/train.orig.$lang \
        | ./sentencepiece/build/src/spm_encode --model=$data_dir/$name.model --output_format=id \
        | sed -e 's/^/1 /' -e 's/$/ 2/' \
        > $data_dir/train.$lang
}

function remove_long_sentences()
{
    input_src=$1
    input_tgt=$2
    max_words=$3

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
    lang=$1
    data_dir=$2
    valid_count=$3

    # separate data for train and valid
    head -n $valid_count $data_dir/train.$lang > $data_dir/valid.$lang
    sed -e "1,${valid_count}d" $data_dir/train.$lang > $data_dir/a.tmp

    # use tmp file to avoid using 'sed -i' because usage is different between GNU and BSD
    mv $data_dir/a.tmp $data_dir/train.$lang
}

pushd $script_dir

cat $data_dir/train.orig.$src $data_dir/train.orig.$tgt > $data_dir/spm_input
./sentencepiece/build/src/spm_train --input=$data_dir/spm_input --model_prefix=$name --vocab_size=$vocab_size --pad_id=3

mv $name.model $name.vocab $data_dir/

encode $src $data_dir $name
encode $tgt $data_dir $name

remove_long_sentences $data_dir/train.$src $data_dir/train.$tgt $max_words

separate $src $data_dir $valid_count
separate $tgt $data_dir $valid_count

popd

