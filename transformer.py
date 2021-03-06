import os
import sys
import time
import math
import argparse
import numpy as np
import torch
import torch.nn as nn
from torch import optim
import torch.nn.functional as F
from torch.utils.tensorboard import SummaryWriter
from nltk.translate.bleu_score import corpus_bleu
import apex

BOS_ID = 1
EOS_ID = 2
PAD_ID = 3

class SimpleAttention(nn.Module):
    def __init__(self, dim):
        super(SimpleAttention, self).__init__()

        self.dim = dim

        self.q_lin = nn.Linear(dim, dim)
        self.k_lin = nn.Linear(dim, dim)
        self.v_lin = nn.Linear(dim, dim)
        self.out_lin = nn.Linear(dim, dim)

    def forward(self, x, memory, attension_mask):
        query = self.q_lin(x)
        key = self.k_lin(memory)
        value = self.v_lin(memory)

        logit = torch.matmul(query, torch.transpose(key, 1, 2))
        attension_weight = F.softmax(logit, dim=2)

        output = torch.matmul(attension_weight, value)

        return self.out_lin(output)

class MultiHeadAttention(nn.Module):
    def __init__(self, n_heads, dim, dropout):
        super(MultiHeadAttention, self).__init__()

        self.n_heads = n_heads
        self.dim = dim
        self.dropout = dropout

        self.q_lin = nn.Linear(dim, dim)
        self.k_lin = nn.Linear(dim, dim)
        self.v_lin = nn.Linear(dim, dim)
        self.out_lin = nn.Linear(dim, dim)

    def forward(self, x, memory, mask):
        batch_size, _, dim = x.shape
        assert dim == self.dim, 'dimension mismatched'

        dim_per_head = dim // self.n_heads

        def split(x):
            x = x.view(batch_size, -1, self.n_heads, dim_per_head)
            return x.transpose(1, 2)

        def combine(x):
            x = x.transpose(1, 2)
            return x.contiguous().view(batch_size, -1, dim)

        q = split(self.q_lin(x))
        k = split(self.k_lin(memory))
        v = split(self.v_lin(memory))

        q = q / math.sqrt(dim_per_head)

        shape = mask.shape
        mask_shape = (shape[0], 1, shape[1], shape[2]) if mask.dim() == 3 else (shape[0], 1, 1, shape[1])
        logit = torch.matmul(q, k.transpose(2, 3))
        logit.masked_fill_(mask.view(mask_shape), -float('inf'))

        weights = F.softmax(logit, dim=-1)
        weights = F.dropout(weights, p=self.dropout, training=self.training)

        output = torch.matmul(weights, v)
        output = combine(output)

        return self.out_lin(output)

class FeedForward(nn.Module):
    def __init__(self, dim_in, dim_hidden, dim_out, dropout):
        super(FeedForward, self).__init__()

        self.dropout = dropout
        self.hidden = nn.Linear(dim_in, dim_hidden)
        self.out = nn.Linear(dim_hidden, dim_out)

    def forward(self, x):
        x = self.hidden(x)
        x = F.relu(x)
        x = self.out(x)
        return F.dropout(x, p=self.dropout, training=self.training)

class ResidualNormalizationWrapper(nn.Module):
    def __init__(self, dim, layer, dropout):
        super(ResidualNormalizationWrapper, self).__init__()

        self.layer = layer
        self.dropout = dropout
        self.normal = nn.LayerNorm(dim)

    def forward(self, input, *args):
        x = self.normal(input)
        x = self.layer(x, *args)
        x = F.dropout(x, p=self.dropout, training=self.training)
        return input + x

class TransformerModel(nn.Module):
    def __init__(self, config, is_decoder):
        super(TransformerModel, self).__init__()

        self.config = config
        self.is_decoder = is_decoder
        self.n_layers = config.n_layers
        self.n_heads = config.n_heads
        self.dim = config.dim
        self.dim_hidden = config.dim * 4
        self.dropout = config.dropout

        self.token_embeddings = nn.Embedding(config.vocab_size, config.dim)
        self.position_embeddings = nn.Embedding(config.n_words, config.dim)

        self.layer_norm_emb = nn.LayerNorm(self.dim)

        self.attentions = nn.ModuleList()
        self.source_attentions = nn.ModuleList()
        self.ffns = nn.ModuleList()
        for _ in range(self.n_layers):
            attention = MultiHeadAttention(self.n_heads, self.dim, self.dropout)
            self.attentions.append(ResidualNormalizationWrapper(self.dim, attention, self.dropout))

            if (is_decoder):
                source_attention = MultiHeadAttention(self.n_heads, self.dim, self.dropout)
                self.source_attentions.append(ResidualNormalizationWrapper(self.dim, source_attention, self.dropout))

            ffn = FeedForward(self.dim, self.dim_hidden, self.dim, self.dropout)
            self.ffns.append(ResidualNormalizationWrapper(self.dim, ffn, self.dropout))

        if is_decoder:
            self.pred_layer = nn.Linear(config.dim, config.vocab_size).to(config.device)

        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_uniform_(p)

    def _get_mask(self, input, causal):
        device = self.config.device
        pad_tensor = torch.empty(1).fill_(PAD_ID).expand_as(input).cpu()
        mask = input.to(dtype=torch.int).cpu() == pad_tensor.cpu()

        if not causal:
            return mask.to(device), mask.to(device)

        batch_size, n_words = input.size()
        shape = (batch_size, n_words, n_words)
        source_mask_np = np.triu(np.ones(shape), k=1).astype('uint8')
        source_mask = torch.from_numpy(source_mask_np) == 1
        pad_mask = mask.unsqueeze(-2)
        source_mask = pad_mask | source_mask

        return mask.to(device), source_mask.to(device)

    def forward(self, input, src_enc=None, src_mask=None, causal=False):
        batch_size, n_sentences = input.size()
        (mask, att_mask) = self._get_mask(input, causal)

        positions = torch.arange(n_sentences).to(dtype=torch.long, device=self.config.device).unsqueeze(0)
        x = self.token_embeddings(input.to(dtype=int))
        x = x + self.position_embeddings(positions).expand_as(x)

        x = self.layer_norm_emb(x)
        x = F.dropout(x, p=self.dropout, training=self.training)
        x[mask] = 0

        for i in range(self.n_layers):
            x = self.attentions[i](x, x, att_mask)

            if self.is_decoder:
                x = self.source_attentions[i](x, src_enc, src_mask)

            x = self.ffns[i](x)
            x[mask] = 0

        return x

    def predict(self, x):
        return F.log_softmax(self.pred_layer(x), dim=-1)

class Trainer(object):
    def __init__(self, config):
        self.config = config

        self.encoder = TransformerModel(config, is_decoder=False).to(config.device)
        self.decoder = TransformerModel(config, is_decoder=True).to(config.device)

        self.optimizer_enc = self._get_optimizer(self.encoder)
        self.scheduler_enc = self._get_scheduler(self.optimizer_enc)

        self.optimizer_dec = self._get_optimizer(self.decoder)
        self.scheduler_dec = self._get_scheduler(self.optimizer_dec)

        if self.config.fp16:
            self.encoder, self.optimizer_enc = apex.amp.initialize(
                self.encoder,
                self.optimizer_enc,
                opt_level='O1' if args.fp16 else 'O0'
            )
            self.decoder, self.optimizer_dec = apex.amp.initialize(
                self.decoder,
                self.optimizer_dec,
                opt_level='O1' if args.fp16 else 'O0'
            )

        self.criterion = LabelSmoothing(config.vocab_size, 0.1).to(config.device)

        model_path = config.best_model_path if config.eval_only else config.model_path
        self.__load_from_model_path(model_path)

        self.start_time = time.time()
        self.bleu_history = []
        self.steps = 0
        self.stats = {
            'sentences': 0,
            'words': 0,
            'loss': 0.0,
        }

        self.writer = SummaryWriter(log_dir=config.tensorboard_log_dir)

        # dummy call to take over learning rate
        # https://discuss.pytorch.org/t/a-problem-occured-when-resuming-an-optimizer/28822
        if 0 < config.last_steps:
            for _ in range(config.last_steps):
                self.step_end(False)

    def save(self, epoch, model_path):
        data = {
            'encoder': self.encoder.state_dict(),
            'decoder': self.decoder.state_dict(),
            'optimizer_enc': self.optimizer_enc.state_dict(),
            'optimizer_dec': self.optimizer_dec.state_dict(),
            'amp': apex.amp.state_dict() if self.config.fp16 else None,
            'batch_size': self.config.batch_size,
            'vocab_size': self.config.vocab_size,
            'n_layers': self.config.n_layers,
            'n_heads': self.config.n_heads,
            'n_words': self.config.n_words,
            'dim': self.config.dim,
            'fp16': self.config.fp16,
            'name': self.config.name,
            'last_epoch': epoch,
            'last_steps': self.steps,
        }
        torch.save(data, model_path)
        print(f'save model to {self.config.model_path}')

    def __load_from_model_path(self, path):
        if not os.path.isfile(path):
            return
        data = torch.load(path, map_location=self.config.device_name)
        self.encoder.load_state_dict(data['encoder'])
        self.decoder.load_state_dict(data['decoder'])
        self.optimizer_enc.load_state_dict(data['optimizer_enc'])
        self.optimizer_dec.load_state_dict(data['optimizer_dec'])
        if self.config.fp16:
            apex.amp.load_state_dict(data['amp'])
        print(f'load model from {path}')

    def _get_optimizer(self, model):
        return optim.Adam(model.parameters(), lr=1.0, betas=(0.9, 0.98), eps=1e-9)

    def _get_scheduler(self, optimizer):
        dim = self.config.dim
        warmup = self.config.warmup_steps

        def update(step):
            current_step = step + 1
            return 2 * dim ** -0.5 * min(current_step ** -0.5, current_step * warmup ** -1.5)

        return optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=update)

    def __generate(self, x):
        self.encoder.eval()
        self.decoder.eval()

        max_len = self.config.n_words
        src_mask = x == PAD_ID
        enc_output = self.encoder(x)

        batch_size, _ = x.shape
        generated = torch.empty(batch_size, max_len).fill_(PAD_ID)
        generated[:,0] = BOS_ID
        generated = generated.to(self.config.device)

        unfinished_sents = torch.ones(batch_size, device=self.config.device)

        for i in range(1, max_len):
            dec_output = self.decoder(generated[:, :i], enc_output, src_mask, True)
            gen_output = self.decoder.predict(dec_output[:, -1])
            _, next_words = torch.max(gen_output, dim=1)

            generated[:, i] = next_words * unfinished_sents + PAD_ID * (1 - unfinished_sents)

            unfinished_sents.mul_(next_words.ne(EOS_ID).long())
            if unfinished_sents.max() == 0:
                break

        return generated.to(dtype=torch.int)

    def __predict(self, x, y, causal):
        enc_output = self.encoder(x)
        dec_output = self.decoder(y[:, :-1], enc_output, x == PAD_ID, causal)

        return self.decoder.predict(dec_output)

    def step(self, x, y):
        self.encoder.train()
        self.decoder.train()

        scores = self.__predict(x, y, True)
        nwords = (y[:, 1:] != PAD_ID).sum().item()
        loss = self.criterion(scores, y[:, 1:], nwords)

        optimizers = [self.optimizer_enc, self.optimizer_dec]

        if self.config.fp16:
            with apex.amp.scale_loss(loss, optimizers) as scaled_loss:
                scaled_loss.backward()
        else:
            loss.backward()

        for optimizer in optimizers:
            optimizer.step()
            optimizer.zero_grad()

        self.stats['loss'] = loss.item()
        self.stats['sentences'] += x.size(0)
        self.stats['words'] += nwords

        self.writer.add_scalar('loss/train', loss, self.steps, time.time())

    def step_end(self, print_log=True):
        self.steps += 1

        if print_log:
            self._print_log()

        self.scheduler_enc.step()
        self.scheduler_dec.step()

    def _print_log(self):
        if self.steps % args.log_interval != 0:
            return

        current_time = time.time()
        elapsed_time = current_time - self.start_time
        lr = self.optimizer_enc.param_groups[0]['lr']
        print('step: {}, loss: {:.2f}, tokens/sec: {:.1f}, lr: {:.6f}'.format(self.steps, self.stats['loss'], self.stats['words'] / elapsed_time, lr))

        self.start_time = current_time
        self.stats['sentences'] = 0
        self.stats['words'] = 0

    def generate_test(self):
        self.encoder.eval()
        self.decoder.eval()

        data = MTDataset(self.config, 'test')
        dataloader = torch.utils.data.DataLoader(data, batch_size=args.batch_size)

        for x, _ in dataloader:
            x = x.to(self.config.device)

            generated = self.__generate(x)

            for i in range(x.size(0)):
                print(' '.join([str(id) for id in x[i].tolist()]))
                print(' '.join([str(int(id)) for id in generated[i].tolist()]))
                # print('input : {}'.format(x[i].tolist()))
                # print('output: {}'.format(generated[i].tolist()))
                # print('')

    def train(self):
        data_type = 'dummy' if self.config.train_test else 'train'
        data_train = MTDataset(self.config, data_type)
        dataloader = torch.utils.data.DataLoader(data_train, batch_size=args.batch_size, shuffle=True)

        print(f'start epoch {epoch}')
        for x, y in dataloader:
            x = x.to(self.config.device)
            y = y.to(self.config.device)
            self.step(x, y)
            self.step_end()

    def evaluate(self, epoch=None, data_type=None):
        self.encoder.eval()
        self.decoder.eval()

        if data_type is None:
            data_type = 'dummy' if self.config.train_test else 'valid'

        data = MTDataset(self.config, data_type)
        if len(data) == 0:
            print('no evaluation data for data_type: {}'.format(data_type))
            return

        dataloader = torch.utils.data.DataLoader(data, batch_size=args.batch_size)

        n_words = 0
        xe_loss = 0
        n_valid = 0
        refs = []
        hyps = []

        for _, (x, y) in enumerate(dataloader):
            x = x.to(self.config.device)
            y = y.to(self.config.device)

            scores = self.__predict(x, y, True)

            y = y[:, 1:]
            nwords = (y != PAD_ID).sum().item()
            loss = self.criterion(scores, y, nwords)

            n_words += nwords
            xe_loss += loss.item() * nwords
            n_valid += (scores.max(2)[1] == y).sum().item()

            generated = self.__generate(x)

            assert len(generated) == len(y), 'size of generated and y are mismatched'
            for i in range(len(generated)):
                hyps.append([id.item() for id in generated[i, 1:] if id != PAD_ID])
                refs.append([[id.item() for id in y[i] if id != PAD_ID]])

        loss = xe_loss / n_words if n_words > 0 else 1e9
        ppl = np.exp(loss)
        acc = 100. * n_valid / n_words if n_words > 0 else 0.

        bleu = corpus_bleu(refs, hyps) * 100.

        if epoch is not None:
            current_time = time.time()
            self.writer.add_scalar('loss/eval', loss, epoch, current_time)
            self.writer.add_scalar('ppl/eval', ppl, epoch, current_time)
            self.writer.add_scalar('acc/eval', acc, epoch, current_time)
            self.writer.add_scalar('bleu/eval', bleu, epoch, current_time)

            self.__udpate_saved_model(bleu, epoch)

        print('==============================')
        print('data_type: {}'.format(data_type))
        print('ppl: {:.2f}'.format(ppl))
        print('acc: {:.2f}'.format(acc))
        print('bleu: {:.2f}'.format(bleu))
        print('==============================')

    def __udpate_saved_model(self, bleu, epoch):
        self.save(epoch, self.config.model_path)

        if len(self.bleu_history) == 0:
            self.bleu_history.append(bleu)
            return

        previous_best = self.bleu_history[0]
        if bleu <= previous_best:
            self.bleu_history.append(bleu)
            return

        self.bleu_history = [bleu]
        self.save(epoch, self.config.best_model_path)

    def is_early_stopping(self):
        return self.config.early_stopping_threshold < len(self.bleu_history)

class LabelSmoothing(nn.Module):
    def __init__(self, size, smoothing):
        super(LabelSmoothing, self).__init__()
        self.criterion = nn.KLDivLoss(reduction='sum')
        self.smoothing = smoothing
        self.size = size

    def forward(self, x, target, nwords):
        x = x.contiguous().view(-1, self.size)
        target = target.contiguous().view(-1)

        true_dist = x.data.clone()
        true_dist.fill_(self.smoothing / (self.size - 2))
        true_dist.scatter_(1, target.unsqueeze(1).to(dtype=torch.long), 1.0 - self.smoothing)
        true_dist[:, PAD_ID] = 0

        mask = torch.nonzero(target.data == PAD_ID)
        if mask.dim() > 0:
            true_dist.index_fill_(0, mask.squeeze(), 0.0)

        return self.criterion(x, true_dist.requires_grad_(False)) / nwords

class MTDataset(torch.utils.data.Dataset):
    def __init__(self, config, type):
        self.config = config
        self.data = {} 

        if type == 'dummy':
            self.__init_with_dummy()
            return

        dataroot = config.dataroot
        for lang in [config.src, config.tgt]:
            path = "{}/{}.{}".format(dataroot, type, lang)
            if not os.path.isfile(path):
                continue

            with open(path, 'r') as f:
                lines = f.read().splitlines()
                data = np.empty((len(lines), self.config.n_words))
                data.fill(PAD_ID)
                for row in range(len(lines)):
                    line = lines[row]
                    if not line:
                        continue

                    array = line.split(' ')
                    word_count = len(array)
                    assert word_count <= self.config.n_words, f'the sentence that has many words we expected. row: {row}, words: {word_count}'

                    for col in range(len(array)):
                        data[row][col] = int(array[col])

            self.data[lang] = torch.from_numpy(data).to(dtype=torch.int)

    def __len__(self):
        if self.config.src in self.data:
            return len(self.data[self.config.src])

        return 0

    def __getitem__(self, idx):
        return (self.data[self.config.src][idx], self.data[self.config.tgt][idx])

    def __init_with_dummy(self):
        data_size = 1000
        vocab_size = self.config.vocab_size
        n_words = self.config.n_words

        data = np.random.randint(PAD_ID+1, vocab_size, size=(data_size, n_words))

        min_words = 5
        eos_indexes = np.random.randint(min_words, n_words, size=data_size)
        for i in range(data_size):
            index = eos_indexes[i]
            data[i][index] = EOS_ID
            data[i][index+1:] = PAD_ID

        data[:, 0] = BOS_ID
        data = torch.from_numpy(data).to(self.config.device, dtype=torch.int)

        self.data[self.config.src] = data.clone()
        self.data[self.config.tgt] = data

class Config():
    def __init__(self, args):
        for key in args.__dict__:
            setattr(self, key, getattr(args, key))
        
        is_cpu = args.cpu or not torch.cuda.is_available()
        self.device_name = "cpu" if is_cpu else "cuda:0"
        self.device = torch.device(self.device_name)

        if args.model_path is None:
            self.model_path = f'{args.dataroot}/{args.name}.pth'
        self.best_model_path = f'{args.dataroot}/{args.name}.best.pth'
        self.tensorboard_log_dir = f'{args.dataroot}/runs/{args.name}'

        self.start_epoch = 1
        self.last_steps = 0
        if os.path.isfile(self.model_path):
            loaded = torch.load(self.model_path, map_location=self.device_name)
            self.__set_from_model('batch_size', loaded)
            self.__set_from_model('vocab_size', loaded)
            self.__set_from_model('n_layers', loaded)
            self.__set_from_model('n_heads', loaded)
            self.__set_from_model('n_words', loaded)
            self.__set_from_model('dim', loaded)
            self.__set_from_model('fp16', loaded)
            self.__set_from_model('name', loaded)
            self.start_epoch = loaded['last_epoch'] + 1
            self.last_steps = loaded['last_steps']

        if is_cpu:
            self.fp16 = False

        for key in self.__dict__:
            print('{}: {}'.format(key, getattr(self, key)))

    def __set_from_model(self, key, loaded):
        assert hasattr(self, key), f'{key} is not found in config'
        assert key in loaded, f'{key} is not found in loaded model'

        config_value = getattr(self, key)
        loaded_value = loaded[key]
        if config_value != loaded_value:
            print('{} is overwritten by loaded value {}'.format(key, loaded_value))
            setattr(self, key, loaded_value)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument('--cpu', action='store_true', help='use cpu')
    parser.add_argument('--dataroot', default='data', help='path to data')
    parser.add_argument('--src', default='ja', help='source language')
    parser.add_argument('--tgt', default='en', help='target language')
    parser.add_argument('--epochs', type=int, default=10, help='epoch count')
    parser.add_argument('--batch_size', type=int, default=2, help='size of batch')
    parser.add_argument('--log_interval', type=int, default=5, help='step num to display log')
    parser.add_argument('--vocab_size', type=int, default=8, help='vocabulary size for copy task')
    parser.add_argument('--n_layers', type=int, default=3, help='number of layers')
    parser.add_argument('--n_heads', type=int, default=8, help='number of heads for multi head attention')
    parser.add_argument('--n_words', type=int, default=10, help='number of words max')
    parser.add_argument('--dim', type=int, default=8, help='dimention of word embeddings')
    parser.add_argument('--dropout', type=int, default=0.1, help='rate of dropout')
    parser.add_argument('--warmup_steps', type=int, default=4000, help='adam lr increases until this steps have passed')
    parser.add_argument('--generate_test', action='store_true', help='only generate translated sentences')
    parser.add_argument('--train_test', action='store_true', help='training copy task with random value')
    parser.add_argument('--eval_only', action='store_true', help='execute evaluation only')
    parser.add_argument('--epochs_by_eval', type=int, default=5, help='evaluate by every this epochs ')
    parser.add_argument('--fp16', action='store_true', help='run model with float16')
    parser.add_argument('--name', default='default', help='name of training, used to model name, log dir name etc')
    parser.add_argument('--early_stopping_threshold', type=int, default=3, help='evaluation count to early stopping')
    parser.add_argument('--model_path', default=None, help='model path')
    args = parser.parse_args()

    config = Config(args)

    os.makedirs(config.tensorboard_log_dir, exist_ok=True)

    trainer = Trainer(config)

    if config.generate_test:
        config.tgt = config.src
        trainer.generate_test()
        sys.exit()

    if config.eval_only:
        trainer.evaluate(data_type='valid')
        trainer.evaluate(data_type='test')
        sys.exit()

    for epoch in range(config.start_epoch, config.start_epoch + config.epochs):
        trainer.train()

        if epoch % config.epochs_by_eval == 0:
            trainer.evaluate(epoch)

            if trainer.is_early_stopping():
                print(f'early stopping epoch: {epoch}')
                break


