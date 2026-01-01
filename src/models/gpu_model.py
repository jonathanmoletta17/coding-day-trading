import torch
import torch.nn as nn
import logging

logging.basicConfig(level=logging.INFO)

class PricePredictorLSTM(nn.Module):
    """
    Modelo LSTM simples para previsão de preços.
    Projetado para rodar na GPU.
    """
    def __init__(self, input_dim, hidden_dim, num_layers, output_dim):
        super(PricePredictorLSTM, self).__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_dim, output_dim)

    def forward(self, x):
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_dim).to(x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_dim).to(x.device)
        
        out, _ = self.lstm(x, (h0, c0))
        out = self.fc(out[:, -1, :])
        return out

def check_gpu_status():
    """Verifica se a GPU está disponível e pronta para uso."""
    if torch.cuda.is_available():
        device_name = torch.cuda.get_device_name(0)
        memory_allocated = torch.cuda.memory_allocated(0) / 1024**3
        memory_reserved = torch.cuda.memory_reserved(0) / 1024**3
        
        logging.info(f"GPU Detectada: {device_name}")
        logging.info(f"Memória Alocada: {memory_allocated:.2f} GB")
        logging.info(f"Memória Reservada: {memory_reserved:.2f} GB")
        return True
    else:
        logging.warning("GPU não detectada. O treinamento será lento na CPU.")
        return False

if __name__ == "__main__":
    check_gpu_status()
    # Exemplo de instanciação
    model = PricePredictorLSTM(input_dim=10, hidden_dim=50, num_layers=2, output_dim=1)
    if torch.cuda.is_available():
        model = model.cuda()
        print("Modelo movido para GPU com sucesso.")
