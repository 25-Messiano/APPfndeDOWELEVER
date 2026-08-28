from abc import ABC, abstractmethod

class FonteBase(ABC):
    @abstractmethod
    def consultar(self, **kwargs):
        raise NotImplementedError
