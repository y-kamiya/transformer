implement transformer model for my practice referring to 
- http://nlp.seas.harvard.edu/2018/04/03/attention.html#loss-computation
- https://github.com/facebookresearch/XLM
- https://qiita.com/halhorn/items/c91497522be27bde17ce

paper: https://papers.nips.cc/paper/7181-attention-is-all-you-need.pdf

### copy task
training
```
$ python transformer.py --train_test --dataroot transformer/data/copy --n_words 10 --n_heads 2 --batch_size 32 --epochs 20 --warmup_steps 500
```
test
```
$ python transformer.py --dataroot data/copy --generate_test --n_words 10 --n_heads 2
```

### use KFTT dataset
```
MODEL_NAME=<model name you like>
DATASET_DIR=<path to dir you like>
```

setup and prepare dataset
```
$ setup.sh
$ prepare_kftt.sh $DATASET_DIR
```

training
```
$ python transformer.py --dataroot $DATASET_DIR --src ja --tgt en --dim 512 --vocab_size 8000 --n_words 64 --batch_size 128 --epochs 200 --log_interval 400 --epochs_by_eval 2 --name $MODEL_NAME --fp16
```

evaluation
```
$ python transformer.py --dataroot $DATASET_DIR --eval_only --src ja --tgt en --name dim512_batch128_fp16 
```

translation test
```
$ cat $DATASET_DIR/test.orig.ja
私は映画館に行きます。

$ translate.sh $DATASET_DIR ja $DATASET_DIR/$MODEL_NAME.best.pth $DATASET_DIR/spm.model

$ cat $DATASET_DIR/result
私は映画館に行きます。
I went to Movie Land.
```
 
you can also use prepare_iwslt2015.sh as same.

details  
https://jsapachehtml.hatenablog.com/entry/2020/05/04/200757


