# Entregas locais

- Ao concluir uma atualização distribuível do aplicativo, gere e valide as builds Linux e Windows com a mesma tag e o mesmo conjunto de fontes.
- Verifique que `dist/atuais/GurpsCalculadora` e `dist/atuais/GurpsCalculadora.exe` foram atualizados, junto com os três ZIPs versionados. O empacotamento faz isso automaticamente quando o par completo está disponível. Para pacotes montados em máquinas separadas, use `python tools/build_archives.py --refresh-current TAG`.
- Se não for possível validar o par, mantenha a versão anterior em `dist/atuais` e informe a pendência. Não sobrescreva pacotes históricos em `dist/releases`.
