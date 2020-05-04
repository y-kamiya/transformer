#!/bin/bash

data_dir=$1
src=$2
model=$3
spm_model=$4

script_dir=$(cd `dirname $0`; pwd)

n_row=$(cat $data_dir/test.orig.$src | wc -l)
n_row=$((n_row * 2))

$script_dir/sentencepiece/build/src/spm_encode --model $spm_model --output_format id $target $data_dir/test.orig.$src \
    | sed -e 's/^/1 /' -e 's/$/ 2/' \
    > $data_dir/test.$src

python $script_dir/transformer.py --generate_test --dataroot $data_dir --src $src --model_path $model --batch_size 32 \
    | tail -n $n_row \
    > $data_dir/result_id

$script_dir/sentencepiece/build/src/spm_decode --model $spm_model --input_format id $data_dir/result_id > $data_dir/result
