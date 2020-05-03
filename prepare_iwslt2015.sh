#!/bin/bash

data_dir=$1

script_dir=$(cd `dirname $0`; pwd)
url="https://wit3.fbk.eu/archive/2015-01/texts/de/en/de-en.tgz"

mkdir -p $data_dir

pushd $data_dir

if [ ! -f en-de.tgz ]; then
    curl -O $url
fi
tar xzvf en-de.tgz

function extract_valid_data()
{
    grep '<seg id' $1 | sed -e 's/<seg id="[0-9]*">\s*//g' -e 's/\s*<\/seg>\s*//g' -e "s/\’/\'/g"
}

extract_valid_data en-de/IWSLT15.TED.dev2010.en-de.en.xml > valid.orig.en
extract_valid_data en-de/IWSLT15.TEDX.dev2012.en-de.en.xml >> valid.orig.en

extract_valid_data en-de/IWSLT15.TED.dev2010.en-de.de.xml > valid.orig.de
extract_valid_data en-de/IWSLT15.TEDX.dev2012.en-de.de.xml >> valid.orig.de

extract_valid_data en-de/IWSLT15.TED.tst2010.en-de.en.xml > test.orig.en
extract_valid_data en-de/IWSLT15.TED.tst2011.en-de.en.xml >> test.orig.en
extract_valid_data en-de/IWSLT15.TED.tst2012.en-de.en.xml >> test.orig.en
extract_valid_data en-de/IWSLT15.TED.tst2013.en-de.en.xml >> test.orig.en
extract_valid_data en-de/IWSLT15.TEDX.tst2013.en-de.en.xml >> test.orig.en

extract_valid_data en-de/IWSLT15.TED.tst2010.en-de.de.xml > test.orig.de
extract_valid_data en-de/IWSLT15.TED.tst2011.en-de.de.xml >> test.orig.de
extract_valid_data en-de/IWSLT15.TED.tst2012.en-de.de.xml >> test.orig.de
extract_valid_data en-de/IWSLT15.TED.tst2013.en-de.de.xml >> test.orig.de
extract_valid_data en-de/IWSLT15.TEDX.tst2013.en-de.de.xml >> test.orig.de

cat en-de/train.tags.en-de.en | sed -e '/^</d' > train.orig.en
cat en-de/train.tags.en-de.de | sed -e '/^</d' > train.orig.de

popd

$script_dir/create_dataset.sh $data_dir en de 1000 0 64

