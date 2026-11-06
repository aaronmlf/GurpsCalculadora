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
perfil de uso pessoal. No Linux, são necessários `binutils` (`readelf`)
e uma base com glibc até 2.39. Para uma build mais portátil, prefira
o Debian 12 (glibc 2.36) do contêiner de referência:

```sh
# Usa só a receita no contexto de build; não envia a pasta do projeto.
docker build --platform linux/amd64 -t gurps-build-linux - < packaging/Dockerfile.linux
docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" \
  --volume "$PWD:/project" gurps-build-linux \
  xvfb-run -a -s '-screen 0 1600x1080x24' sh packaging/build_linux.sh
```

Monte preferencialmente uma cópia limpa dos fontes. O contêiner não
precisa de acesso à sessão gráfica do usuário. Antes de empacotar, o
script inspeciona o bootloader e todos os ELF dentro do executável:
recusa dependências acima de `GLIBC_2.39` ou de ABI privada da glibc.
O maior requisito encontrado fica em `glibc_required_by_elf` no
relatório; a compatibilidade em uma distribuição deve ser confirmada
também com o teste de abertura nela.

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

## Atualizar dist/atuais

A segunda build de uma mesma tag atualiza automaticamente os executáveis
em `dist/atuais`, desde que os dois pacotes verificados estejam juntos em
`dist/releases/<tag>/` e venham do mesmo conjunto de fontes. Uma build
isolada ou uma verificação com erro não substitui a versão atual.

A pasta mantém os nomes fixos `GurpsCalculadora` e `GurpsCalculadora.exe`
para abrir diretamente, os três ZIPs identificados pela tag (atalhos no
Linux quando disponíveis, cópias no Windows) e o `current.json` com a tag
em uso. Pacotes e ZIPs versionados anteriores são preservados.

Se as builds foram produzidas em máquinas diferentes, reúna as pastas
`linux/` e `windows/` completas sob a mesma tag, incluindo os manifestos
e checksums, e execute no projeto:

```sh
python tools/build_archives.py --refresh-current v1.6.0-mapa.3
```

O comando não recompila e não publica no GitHub. Se o Windows impedir a
troca de um executável em uso, feche o aplicativo e repita o comando.

## Verificar pacotes existentes

```sh
python tools/build_archives.py --verify dist/releases/v1.6.0/linux
# Com PyInstaller e binutils instalados, confira também o executável extraído:
python tools/build_archives.py --verify-linux-binary ./GurpsCalculadora
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
