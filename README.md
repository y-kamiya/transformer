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
