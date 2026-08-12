"""
Módulo de internacionalização (i18n) para a Calculadora GURPS 4e
"""
import json
import os
from typing import Dict, Any


class I18n:
    """Classe para gerenciar internacionalização."""
    
    def __init__(self, default_language: str = "pt_BR"):
        """
        Inicializa o sistema i18n.
        
        Args:
            default_language: Idioma padrão (pt_BR ou en_US)
        """
        self.current_language = default_language
        self.translations: Dict[str, Dict[str, str]] = {}
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._load_translations()
    
    def _load_translations(self):
        """Carrega todas as traduções disponíveis."""
        i18n_dir = os.path.join(self.base_dir, "i18n")
        
        for lang_file in ["pt_BR.json", "en_US.json"]:
            lang_path = os.path.join(i18n_dir, lang_file)
            if os.path.exists(lang_path):
                with open(lang_path, 'r', encoding='utf-8') as f:
                    lang_code = lang_file.replace('.json', '')
                    self.translations[lang_code] = json.load(f)
    
    def set_language(self, language: str):
        """
        Define o idioma atual.
        
        Args:
            language: Código do idioma (pt_BR ou en_US)
        """
        if language in self.translations:
            self.current_language = language
    
    def get_language(self) -> str:
        """Retorna o idioma atual."""
        return self.current_language
    
    def t(self, key: str, **kwargs) -> str:
        """
        Traduz uma chave para o idioma atual.
        
        Args:
            key: Chave da tradução
            **kwargs: Argumentos para formatação
            
        Returns:
            Texto traduzido
        """
        if self.current_language in self.translations:
            text = self.translations[self.current_language].get(key, key)
        else:
            text = key
        
        # Formata argumentos se fornecidos
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, IndexError):
                pass
        
        return text
    
    def get_available_languages(self) -> Dict[str, str]:
        """
        Retorna idiomas disponíveis.
        
        Returns:
            Dict com código: nome do idioma
        """
        return {
            "pt_BR": "Português (Brasil)",
            "en_US": "English (US)"
        }
    
    def get_current_language_name(self) -> str:
        """Retorna nome do idioma atual."""
        languages = self.get_available_languages()
        return languages.get(self.current_language, self.current_language)


# Instância global
_i18n = None


def get_i18n() -> I18n:
    """Retorna instância global do i18n."""
    global _i18n
    if _i18n is None:
        _i18n = I18n()
    return _i18n


def t(key: str, **kwargs) -> str:
    """
    Função de conveniência para tradução.
    
    Args:
        key: Chave da tradução
        **kwargs: Argumentos para formatação
        
    Returns:
        Texto traduzido
    """
    return get_i18n().t(key, **kwargs)