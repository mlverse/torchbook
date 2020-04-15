# https://pytorch.org/tutorials/beginner/torchtext_translation_tutorial.html

# https://github.com/bentrevett/pytorch-seq2seq


import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F

from torchtext.data import Field, BucketIterator
from torchtext.datasets import IWSLT

import random
import numpy as np
import math

src = Field(tokenize = "spacy",
            tokenizer_language="en",
            init_token = '<sos>',
            eos_token = '<eos>',
            lower = True)

trg = Field(tokenize = "spacy",
            tokenizer_language="fr",
            init_token = '<sos>',
            eos_token = '<eos>',
            lower = True)
# Automatically adding <sos> as the first token and <eos> as the last token of each sentence
#Tokenizing each sentence using the tokenize method
train_data, valid_data, test_data = IWSLT.splits(exts = ('.en', '.fr'), fields = (src, trg))
len(train_data.examples)
len(valid_data.examples)
len(test_data.examples)

vars(train_data.examples[0])
vars(train_data.examples[1000])
vars(train_data.examples[100000])

src.build_vocab(train_data, min_freq = 2)
trg.build_vocab(train_data, min_freq = 2)

len(src.vocab)
len(trg.vocab)

src.vocab.stoi 
trg.vocab.stoi

src.vocab.itos[0]
src.vocab.itos[1]
src.vocab.itos[2]
src.vocab.itos[3]

trg.vocab.itos[0]
trg.vocab.itos[1]
trg.vocab.itos[2]
trg.vocab.itos[3]


#device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
device = "cpu"
batch_size = 8

# Defines an iterator that batches examples of similar lengths together.
# Minimizes amount of padding needed while producing freshly shuffled batches for each new epoch.
train_iterator, valid_iterator, test_iterator = BucketIterator.splits(
    (train_data, valid_data, test_data),
    batch_size = batch_size,
    device = device)
    
src_len_in_tokens = (np.array([len(el.src) for el in train_iterator.data()]))
np.min(src_len_in_tokens), np.median(src_len_in_tokens), np.max(src_len_in_tokens)

trg_len_in_tokens = (np.array([len(el.trg) for el in train_iterator.data()]))
np.min(trg_len_in_tokens), np.median(trg_len_in_tokens), np.max(trg_len_in_tokens)

batch = next(iter(train_iterator))
batch.src.shape
batch.trg.shape

batch.src[ :, 0]
batch.src[ :, 1]

num_input_features = len(src.vocab)
encoder_embedding_dim = 32
encoder_hidden_dim = 64
encoder_dropout = 0.5
decoder_hidden_dim = 64

# GRU: compare with keras
# normally, returns 2D tensor with shape (batch_size, units)
# if return_state: a list of tensors. The first tensor is the output. 
#                  The remaining tensors are the last states, each with shape (batch_size, units).
# if return_sequences: 3D tensor with shape (batch_size, timesteps, units).

# so torch returns a tuple of: 
#   - outputs (corresponding to keras' return_sequences = true)
#   - last state(s) (like keras with return_state)

class Encoder(nn.Module):
    def __init__(self, num_input_features, embedding_dim, encoder_hidden_dim, decoder_hidden_dim, dropout):
        super().__init__()
        self.num_input_features = num_input_features
        self.embedding_dim = embedding_dim
        self.encoder_hidden_dim = encoder_hidden_dim
        self.decoder_hidden_dim = decoder_hidden_dim
        self.dropout = dropout
        self.embedding = nn.Embedding(num_input_features, embedding_dim)
        # constructor takes number of input features (will come from embedding) and hidden_size
        self.rnn = nn.GRU(embedding_dim, encoder_hidden_dim, bidirectional = True)
        self.fc = nn.Linear(encoder_hidden_dim * 2, decoder_hidden_dim)
        self.dropout = nn.Dropout(dropout)
    def forward(self, src):
        # src:         seq_len * bs
        # embedded:    seq_len * bs * embedding_dim
        # meaning:     each input token has been embedded to degree embedding_dim
        embedded = self.dropout(self.embedding(src))
        # output:      seq_len * bs * (2 * hidden_size)
        # meaning:     tensor containing the output features h_t for each t (!)
        # hidden:      2 * bs * hidden_size
        # meaning:     tensor containing the hidden state for t = seq_len
        outputs, hidden = self.rnn(embedded)
        # concatenate last state from both directions
        # input size to fc then is bs * 2 * hidden_size
        hidden = torch.tanh(self.fc(torch.cat((hidden[-2,:,:], hidden[-1,:,:]), dim = 1)))
        # hidden is now bs * decoder_hidden_dim
        return outputs, hidden

encoder = Encoder(num_input_features, encoder_embedding_dim, encoder_hidden_dim, decoder_hidden_dim, encoder_dropout).to(device)

encoder_output = encoder.forward(batch.src)
[t.size() for t in encoder_output]
# [torch.Size([357, 8, 128]), torch.Size([8, 64])]
decoder_hidden = encoder_output[1]
encoder_outputs = encoder_output[0]

###

attention_dim = 8

class Attention(nn.Module):
    def __init__(self, encoder_hidden_dim, decoder_hidden_dim, attention_dim):
        super().__init__()
        self.encoder_hidden_dim = encoder_hidden_dim
        self.decoder_hidden_dim = decoder_hidden_dim
        self.attention_in = (encoder_hidden_dim * 2) + decoder_hidden_dim
        self.attention = nn.Linear(self.attention_in, attention_dim)
    def forward(self, decoder_hidden, encoder_outputs):
        # seq_len
        src_len = encoder_outputs.shape[0]
        # bs * decoder_hidden_dim ->  bs * 1 * decoder_hidden_dim -> bs * seq_len * decoder_hidden_dim
        # repeats hidden for every source token
        repeated_decoder_hidden = decoder_hidden.unsqueeze(1).repeat(1, src_len, 1)
        # seq_len * bs * (2 * hidden) -> bs * seq_len * (2 * hidden)
        encoder_outputs = encoder_outputs.permute(1, 0, 2)
        # after cat: bs * seq_len * (hidden + 2 * hidden)
        # so this concatenates, for every batch item and source token, hidden state from decoder
        # (encoder, initially) and encoder output
        # energy then is bs * seq_len * attention_dim
        energy = torch.tanh(self.attention(torch.cat((repeated_decoder_hidden, encoder_outputs), dim = 2)))
        # bs * seq_len 
        # a score for every source token
        attention = torch.sum(energy, dim=2)
        return F.softmax(attention, dim=1)

attention = Attention(encoder_hidden_dim, decoder_hidden_dim, attention_dim).to(device)

# first is hidden, second is output
# first time is encoder hidden, later hidden will be DECODER hidden state!
a = attention(decoder_hidden, encoder_outputs)
a.size()
# torch.Size([8, 357])

###

num_output_features = len(trg.vocab)
decoder_embedding_dim = 32
decoder_dropout = 0.5

class Decoder(nn.Module):
    def __init__(self, num_output_features, embedding_dim, encoder_hidden_dim, decoder_hidden_dim, dropout, attention):
        super().__init__()
        self.embedding_dim = embedding_dim
        self.encoder_hidden_dim = encoder_hidden_dim
        self.decoder_hidden_dim = decoder_hidden_dim
        self.num_output_features = num_output_features
        self.dropout = dropout
        self.attention = attention
        self.embedding = nn.Embedding(num_output_features, embedding_dim)
        self.rnn = nn.GRU((encoder_hidden_dim * 2) + embedding_dim, decoder_hidden_dim)
        self.out = nn.Linear(self.attention.attention_in + embedding_dim, num_output_features)
        self.dropout = nn.Dropout(dropout)
    def _weighted_encoder_rep(self, decoder_hidden, encoder_outputs):
        # bs * seq_len
        a = self.attention(decoder_hidden, encoder_outputs)
        # bs * 1 * seq_len
        a = a.unsqueeze(1)
        # bs * 357 * 128
        encoder_outputs = encoder_outputs.permute(1, 0, 2)
        # bs * 1 * 128
        weighted_encoder_rep = torch.bmm(a, encoder_outputs)
        # 1 * bs * 128
        weighted_encoder_rep = weighted_encoder_rep.permute(1, 0, 2)
        return weighted_encoder_rep
    def forward(self, input, decoder_hidden, encoder_outputs):
        # 1 * bs
        input = input.unsqueeze(0)
        # 1 * bs * 32
        embedded = self.dropout(self.embedding(input))
        # 1 * bs * 128
        weighted_encoder_rep = self._weighted_encoder_rep(decoder_hidden, encoder_outputs)
        # concatenate input embedding and 
        # embedded: 1 * bs * 32
        # weighted_encoder_rep: 1 * bs * 128
        # rnn_input: 1 * 8 * 160
        rnn_input = torch.cat((embedded, weighted_encoder_rep), dim = 2)
        # output: 1 * bs * 64
        # decoder_hidden: 1 * bs * 64 (after unsqueeze)
        output, decoder_hidden = self.rnn(rnn_input, decoder_hidden.unsqueeze(0))
        embedded = embedded.squeeze(0)
        output = output.squeeze(0)
        weighted_encoder_rep = weighted_encoder_rep.squeeze(0)
        output = self.out(torch.cat((output, weighted_encoder_rep, embedded), dim = 1))
        # output is bs * num_output_features
        return output, decoder_hidden.squeeze(0)


decoder = Decoder(num_output_features, decoder_embedding_dim, encoder_hidden_dim, decoder_hidden_dim, decoder_dropout, attention).to(device)
output = batch.trg[0,:]
# decoder.forward(output, decoder_hidden, encoder_outputs)

class Seq2Seq(nn.Module):
    def __init__(self, encoder, decoder, device):
        super().__init__()
        self.encoder = encoder
        self.decoder = decoder
        self.device = device
    def forward(self, src, trg, teacher_forcing_ratio = 0.5):
        batch_size = src.shape[1]
        max_len = trg.shape[0]
        trg_vocab_size = self.decoder.num_output_features
        outputs = torch.zeros(max_len, batch_size, trg_vocab_size).to(self.device)
        encoder_outputs, hidden = self.encoder(src)
        # first input to the decoder is the <sos> token
        output = trg[0,:]
        for t in range(1, max_len):
            output, hidden = self.decoder(output, hidden, encoder_outputs)
            outputs[t] = output
            teacher_force = random.random() < teacher_forcing_ratio
            top1 = output.max(1)[1]
            output = (trg[t] if teacher_force else top1)
        return outputs

model = Seq2Seq(encoder, decoder, device).to(device)


def init_weights(m):
    for name, param in m.named_parameters():
        if 'weight' in name:
            nn.init.normal_(param.data, mean=0, std=0.01)
        else:
            nn.init.constant_(param.data, 0)
model.apply(init_weights)

optimizer = optim.Adam(model.parameters())
pad_idx = trg.vocab.stoi['<pad>']
criterion = nn.CrossEntropyLoss(ignore_index = pad_idx)

def train(model, iterator, optimizer, criterion, clip):
    model.train()
    epoch_loss = 0
    for _, batch in enumerate(iterator):
        src = batch.src
        trg = batch.trg
        optimizer.zero_grad()
        # seq_len * bs * num_output_features
        output = model(src, trg)
        # ((seq_len - 1) * bs) * num_output_features (output[1:] is (seq_len - 1) * bs * num_output_features))
        output = output[1:].view(-1, output.shape[-1])
        # (trg_len - 1) 
        trg = trg[1:].view(-1)
        loss = criterion(output, trg)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), clip)
        optimizer.step()
        epoch_loss += loss.item()
    return epoch_loss / len(iterator)

def evaluate(model, iterator, criterion):
    model.eval()
    epoch_loss = 0
    with torch.no_grad():
        for _, batch in enumerate(iterator):
            src = batch.src
            trg = batch.trg
            output = model(src, trg, 0) #turn off teacher forcing
            output = output[1:].view(-1, output.shape[-1])
            trg = trg[1:].view(-1)
            loss = criterion(output, trg)
            epoch_loss += loss.item()
    return epoch_loss / len(iterator)


n_epochs = 10
clip = 1

best_valid_loss = float('inf')

for epoch in range(n_epochs):
    train_loss = train(model, train_iterator, optimizer, criterion, clip)
    valid_loss = evaluate(model, valid_iterator, criterion)
    print(f'Epoch: {epoch+1:02}')
    print(f'\tTrain Loss: {train_loss:.3f} | Train PPL: {math.exp(train_loss):7.3f}')
    print(f'\t Val. Loss: {valid_loss:.3f} |  Val. PPL: {math.exp(valid_loss):7.3f}')

test_loss = evaluate(model, test_iterator, criterion)

print(f'| Test Loss: {test_loss:.3f} | Test PPL: {math.exp(test_loss):7.3f} |')





