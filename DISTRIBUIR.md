# Distribuir o ResourceStudio

1. Copia a pasta completa para o computador do utilizador.
2. Executa `run.bat`.
3. O programa procura primeiro `runtime\python.exe` e depois o Python instalado no sistema.
4. As dependências só são instaladas quando não forem encontradas.
5. O painel abre localmente em `http://127.0.0.1:8777`.

O programa funciona offline depois das dependências estarem instaladas. O
`lupa` não é obrigatório para usar a ferramenta; é apenas usado nos testes de
paridade do desenvolvimento.

Para encerrar, executa `stop.bat`.
