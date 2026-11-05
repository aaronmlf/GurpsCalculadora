# Compilação e verificação de pacotes

Os usuários finais só precisam do ZIP da sua plataforma. A compilação
para manutenção usa Python 3.11 ou superior, Tk funcional e arquitetura
x86-64. Não é necessário instalar bibliotecas Python para executar a
versão empacotada.

## Gerar os ZIPs

Execute na plataforma de destino, com acesso a uma sessão gráfica:

```sh
./packaging/build_linux.sh
# Em Linux sem desktop, use: xvfb-run -a ./packaging/build_linux.sh
```

```bat
packaging\build_windows.bat
```

Os scripts instalam as versões de ferramentas fixadas nos arquivos
`requirements-build*.txt`. Também é possível chamar
`python tools/build_archives.py` com todas as versões já instaladas. No
Windows, use o Python e Tk de 64 bits. Uma build feita sob Wine usa um
Python Windows x64 e é identificada como `wine` no relatório; não
substitui validação em Windows nativo. Use um prefixo Wine separado do
perfil de uso pessoal. No Linux, compile na distribuição mais antiga
que deseja suportar e confirme a compatibilidade nela.

A tag padrão vem de `version.py`. Uma compilação de validação separada
pode usar `--tag v1.6.0-verificacao.1` se a versão atual for `1.6.0`.
Uma tag de outra versão é recusada. Uma pasta de release existente
nunca é sobrescrita.

O fluxo copia exclusivamente as entradas revisadas em
`source-files.txt` e `resources.txt` para uma pasta temporária. Roda
os testes e PyInstaller a partir da mesma cópia, verifica arquitetura e
conteúdo dos JSONs incorporados e abre a janela Tk do executável com
perfil vazio. Só depois gera e valida os ZIPs. Os arquivos publicados
localmente ficam em `dist/releases/<tag>/<linux|windows>/`:

- `GurpsCacul_Linux.zip` ou `GurpsCacul_Windows.zip`: executável recém-testado e instruções.
- `GurpsCalculadora_Codigo_Fonte.zip`: fontes, testes, scripts e catálogos permitidos.
- `release.json`: versão, plataforma, ambiente, teste de abertura, hashes e lista de fontes.
- `SHA256SUMS.txt`: hashes dos ZIPs.

Nada é enviado para Git ou GitHub pelo script. Antes de anexar os ZIPs à
release, compare `source_sha256` de Linux e Windows: ambos devem ter
sido gerados das mesmas fontes. Os ZIPs históricos na raiz e em `dist/`
não são usados como entrada. O hash do executável em `release.json`
liga o ZIP ao binário testado; não é uma assinatura digital.

A verificação do GitHub Actions está configurada para rodar o mesmo
fluxo no Linux e em Windows nativo quando a alteração chegar ao GitHub.
Ela não anexa arquivos nem publica releases.

## Verificar pacotes existentes

```sh
python tools/build_archives.py --verify dist/releases/v1.6.0/linux
```

Esse comando verifica integridade, inventário e consistência sem rodar
o executável. Não prova autoria: compare os hashes com os que foram
publicados pelo mantenedor. Para testar novamente a abertura de um
executável extraído, use `python tools/verify_gui_launch.py <executável>`
em uma sessão gráfica. Para Wine, indique `wine <executável.exe>` e
defina `WINEPREFIX` apontando para um prefixo isolado.

## Manter as listas de arquivos

Ao adicionar um arquivo do projeto, revise seu conteúdo antes de
incluí-lo em `packaging/source-files.txt`. Um JSON de uso do aplicativo
entra somente em `packaging/resources.txt`, que também o inclui no ZIP
de fontes. Nenhum diretório é vasculhado recursivamente para incluir
arquivos novos. Não adicione livros, imagens do acervo, arquivos
pessoais, credenciais ou dados de sessão.
