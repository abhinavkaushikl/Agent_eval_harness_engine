# expect: abstain:dead_end -- a torch training loop (.backward()) is model_training, which no record covers; labelling it code_generation instead would be a reach.
import torch
from torch import nn


def train(model: nn.Module, batches: list[tuple[torch.Tensor, torch.Tensor]], epochs: int) -> float:
    optimiser = torch.optim.SGD(model.parameters(), lr=0.01)
    loss_fn = nn.MSELoss()
    loss = torch.tensor(0.0)
    for _ in range(epochs):
        for inputs, targets in batches:
            optimiser.zero_grad()
            loss = loss_fn(model(inputs), targets)
            loss.backward()
            optimiser.step()
    return float(loss)
