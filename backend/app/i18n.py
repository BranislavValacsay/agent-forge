import re
from typing import Any


SK_MESSAGES = {
    "Root access required": "Vyžaduje sa root prístup",
    "Agent not found": "Agent sa nenašiel",
    "CrewAI agent requires a provider and model": "CrewAI agent vyžaduje provider a model",
    "CrewAI member field is too long": "Pole člena CrewAI je príliš dlhé",
    "CrewAI member requires role, goal and backstory": "Člen CrewAI vyžaduje rolu, cieľ a backstory",
    "CrewAI process must be sequential or hierarchical": "CrewAI proces musí byť sekvenčný alebo hierarchický",
    "CrewAI requires 1 to 20 members": "CrewAI vyžaduje 1 až 20 členov",
    "CrewAI requires 1 to 50 tasks": "CrewAI vyžaduje 1 až 50 úloh",
    "CrewAI task field is too long": "Pole úlohy CrewAI je príliš dlhé",
    "CrewAI task requires name, description, expected output and member": "Úloha CrewAI vyžaduje názov, popis, očakávaný výstup a člena",
    "Every CrewAI member must be an object": "Každý člen CrewAI musí byť objekt",
    "Every CrewAI task must be an object": "Každá úloha CrewAI musí byť objekt",
    "MCP agent requires an MCP server and tool name": "MCP agent vyžaduje MCP server a názov nástroja",
    "Selected CrewAI provider/model is unavailable": "Vybraný CrewAI provider alebo model nie je dostupný",
    "Selected MCP server does not exist": "Vybraný MCP server neexistuje",
    "Selected MCP server is disabled": "Vybraný MCP server je zakázaný",
    "Selected MCP server not found": "Vybraný MCP server sa nenašiel",
    "Selected MCP tool is not present in the synchronized catalog": "Vybraný MCP nástroj nie je v synchronizovanom katalógu",
    "Selected model does not belong to the provider": "Vybraný model nepatrí providerovi",
    "Email is already registered": "E-mail je už zaregistrovaný",
    "Invalid email or password": "Neplatný e-mail alebo heslo",
    "Registration is disabled": "Registrácia je zakázaná",
    "Do not put credentials in the MCP URL; use secret headers": "Nevkladaj prihlasovacie údaje do MCP URL; použi tajné hlavičky",
    "MCP endpoint must include http:// or https://": "MCP endpoint musí obsahovať http:// alebo https://",
    "MCP secret headers contain invalid characters": "Tajné MCP hlavičky obsahujú neplatné znaky",
    "MCP server not found": "MCP server sa nenašiel",
    "Stored MCP secret cannot be decrypted": "Uložený MCP secret sa nedá dešifrovať",
    "stdio MCP server requires a command argument array": "stdio MCP server vyžaduje pole argumentov príkazu",
    "stdio command contains an invalid null byte": "stdio príkaz obsahuje neplatný nulový bajt",
    "stdio servers are discovered and tested by an MCP worker": "stdio servery zisťuje a testuje MCP worker",
    "stdio servers are tested by the execution worker": "stdio servery testuje exekučný worker",
    "Pipeline not found": "Pipeline sa nenašla",
    "Run access required": "Vyžaduje sa oprávnenie na spustenie",
    "Provider URL must include http:// or https://": "URL providera musí obsahovať http:// alebo https://",
    "Provider not found": "Provider sa nenašiel",
    "Cancel the active run before retrying it": "Pred opakovaním najprv zastav aktívny run",
    "Edit access required": "Vyžaduje sa oprávnenie na úpravu",
    "Only queued or running runs can be cancelled": "Zastaviť možno iba run v stave queued alebo running",
    "Run not found": "Run sa nenašiel",
    "Write access required": "Vyžaduje sa oprávnenie na zápis",
    "Invalid or disabled worker": "Worker je neplatný alebo zakázaný",
    "Job lease expired": "Lease úlohy vypršal",
    "Job lease is not valid": "Lease úlohy nie je platný",
    "Registration token is invalid, expired, or already used": "Registračný token je neplatný, expirovaný alebo už použitý",
    "Run or step disappeared": "Run alebo krok už neexistuje",
    "Worker not found": "Worker sa nenašiel",
    "Worker token required": "Vyžaduje sa token workera",
    "Invalid session": "Neplatná relácia",
    "Not authenticated": "Používateľ nie je prihlásený",
    "User unavailable": "Používateľ nie je dostupný",
}

SK_PATTERNS = (
    (r"^Agent is used by pipeline\(s\): (.+)\. Remove its nodes first\.$", r"Agent používa pipeline: \1. Najprv odstráň jej nodes."),
    (r"^CrewAI task references unknown role: (.+)$", r"Úloha CrewAI odkazuje na neznámu rolu: \1"),
    (r"^Duplicate CrewAI role: (.+)$", r"Duplicitná rola CrewAI: \1"),
    (r"^Duplicate CrewAI task name: (.+)$", r"Duplicitný názov úlohy CrewAI: \1"),
    (r"^MCP connection failed: (.+)$", r"MCP spojenie zlyhalo: \1"),
    (r"^MCP secret header '(.+)' is reserved$", r"Tajná MCP hlavička „\1“ je rezervovaná"),
    (r"^MCP server is used by agent\(s\): (.+)$", r"MCP server používajú agenti: \1"),
    (r"^AI provider/model missing for (.+)$", r"Agentovi \1 chýba AI provider alebo model"),
    (r"^Agent for step (.+) no longer exists$", r"Agent kroku \1 už neexistuje"),
    (r"^MCP secret for (.+) is invalid$", r"MCP secret pre \1 je neplatný"),
    (r"^MCP server missing for (.+)$", r"Agentovi \1 chýba MCP server"),
    (r"^MCP server (.+) is disabled$", r"MCP server \1 je zakázaný"),
)


def localize_detail(detail: Any, accept_language: str | None) -> Any:
    if not (accept_language or "").lower().startswith("sk") or not isinstance(detail, str):
        return detail
    if detail in SK_MESSAGES:
        return SK_MESSAGES[detail]
    for pattern, replacement in SK_PATTERNS:
        if re.match(pattern, detail):
            return re.sub(pattern, replacement, detail)
    return detail
