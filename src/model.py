"""
model.py - Arquitectura de red neuronal convolucional 1D para clasificacion EDS.

Proporciona:
    - Spectra1DCNN(nn.Module): Red convolucional 1D simple disenada para
      procesar espectros unidimensionales de rayos X y clasificar materiales.
"""

import torch
import torch.nn as nn


class Spectra1DCNN(nn.Module):
    """
    Red neuronal convolucional 1D para clasificacion de espectros EDS.

    Arquitectura:
        - Bloque convolucional 1: Conv1d -> BatchNorm1d -> ReLU -> MaxPool1d
        - Bloque convolucional 2: Conv1d -> BatchNorm1d -> ReLU -> MaxPool1d
        - Capa lineal final (clasificacion)

    La red espera espectros unidimensionales con una dimension de canal
    (batch_size, 1, spectrum_length). Los canales de entrada se fijan en 1
    ya que cada espectro EDS es una senial 1D.

    Args:
        num_classes (int): Numero de clases de materiales a clasificar.
        in_channels (int): Numero de canales de entrada (default: 1 para EDS).
        conv1_out_channels (int): Filtros en la primera capa convolucional.
        conv2_out_channels (int): Filtros en la segunda capa convolucional.
        kernel_size (int): Tamano del nucleo convolucional (shared entre capas).

    Shape de entrada:
        Tensor de forma (batch_size, 1, spectrum_length)

    Shape de salida:
        Tensor de forma (batch_size, num_classes) con logits no normalizados.
    """

    def __init__(
        self,
        num_classes,
        in_channels=1,
        conv1_out_channels=32,
        conv2_out_channels=64,
        kernel_size=5,
    ):
        super(Spectra1DCNN, self).__init__()

        # Bloque convolucional 1
        self.conv_block_1 = nn.Sequential(
            nn.Conv1d(in_channels, conv1_out_channels, kernel_size=kernel_size),
            nn.BatchNorm1d(conv1_out_channels),
            nn.ReLU(inplace=True),
            nn.MaxPool1d(kernel_size=2, stride=2),
        )

        # Bloque convolucional 2
        self.conv_block_2 = nn.Sequential(
            nn.Conv1d(
                conv1_out_channels, conv2_out_channels, kernel_size=kernel_size
            ),
            nn.BatchNorm1d(conv2_out_channels),
            nn.ReLU(inplace=True),
            nn.MaxPool1d(kernel_size=2, stride=2),
        )

        # Capa lineal final de clasificacion
        self.classifier = nn.Linear(conv2_out_channels, num_classes)

    def forward(self, x):
        """
        Paso hacia adelante (forward pass).

        Args:
            x (Tensor): Tensor de entrada de forma (batch_size, 1, spectrum_length).

        Returns:
            Tensor: Logits de clasificacion de forma (batch_size, num_classes).
        """
        # Aplicar bloques convolucionales
        x = self.conv_block_1(x)   # (B, conv1_out_channels, reduced_length)
        x = self.conv_block_2(x)   # (B, conv2_out_channels, further_reduced)

        # AdaptiveAvgPool1d asegura un tamano de salida fijo independientemente
        # de la longitud del espectro de entrada. Esto permite usar la red con
        # espectros de diferentes resoluciones sin ajustar la capa lineal.
        x = nn.functional.adaptive_avg_pool1d(x, 1)  # (B, conv2_out_channels, 1)

        # Aplanar dimension de longitud para la capa lineal
        x = x.squeeze(-1)  # (B, conv2_out_channels)

        # Capa de clasificacion final
        logits = self.classifier(x)  # (B, num_classes)

        return logits
