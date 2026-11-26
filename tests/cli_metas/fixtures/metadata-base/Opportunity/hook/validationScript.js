// Integracao PipeImob (TRM), epico 01, historia 1.1 -- FR-003 / AC-003 / AC-004.
//
// O gate de completude: marcar o negocio como "Proposta aceita" exige os campos que o
// TRM precisa para abrir a transacao. Campo faltando BLOQUEIA a transicao com mensagem
// que nomeia o campo -- nunca vira erro de API do parceiro (D-152).
//
// A lista NAO mora aqui (AC-004): mora na Setting `PIPEIMOB_REQUIRED_FIELDS`, um JSON
// de caminhos pontuados sobre {opportunity, contact, product}, lida por validationData.
// Sem a Setting o gate e um no-op -- e assim que um tenant sem PipeImob fica intocado.
// Cada caminho pode ter rotulo: "contact.cpf|CPF do comprador".
var ALVO = 'Proposta aceita';

function ler(raiz, caminho) {
	var atual = raiz;
	var partes = caminho.split('.');
	for (var i = 0; i < partes.length; i++) {
		if (atual == null) return undefined;
		atual = atual[partes[i]];
	}
	return atual;
}

function vazio(v) {
	if (v == null) return true;
	if (typeof v === 'string') return v.trim() === '';
	if (Array.isArray(v)) return v.length === 0;
	// Date do Mongo: objeto sem chaves enumeraveis, mas preenchido (instanceof nao vale entre realms do vm)
	if (Object.prototype.toString.call(v) === '[object Date]') return false;
	if (typeof v === 'object') return Object.keys(v).length === 0;
	return false;
}

try {
	// Pre-imagem: `_original` (runtime novo, dentro da transacao) ou `original[0]` (find declarado, runtime antigo).
	var original = (extraData || {})._original || ((extraData || {}).original || [])[0] || {};
	var subFaseNova = data.subPhase;
	var subFaseAntes = original.subPhase;
	// Lista com um elemento (maxSelected: 1) chega como string; toleramos array.
	if (Array.isArray(subFaseNova)) subFaseNova = subFaseNova[0];
	if (Array.isArray(subFaseAntes)) subFaseAntes = subFaseAntes[0];

	if (subFaseNova !== ALVO || subFaseAntes === ALVO) {
		return { success: true };
	}

	// Locacao nao passa pelo PipeImob (TRM e fluxo de venda; CRM #5502, A7): sem acionamento, sem gate.
	var negocio = data.transactionType;
	if (Array.isArray(negocio)) negocio = negocio[0];
	if (negocio === 'locacao') {
		return { success: true };
	}

	// A Setting e lida como sistema (validationData.asSystem). Chave AUSENTE significa que a leitura
	// nao aconteceu ou falhou -- e o gate barra (fail-closed): passar em silencio e o que a D-152 proibe.
	// Lista VAZIA lida com sucesso = Setting inexistente = gate desligado neste tenant.
	var settings = (extraData || {}).pipeimobRequired;
	if (settings === undefined) {
		var motivo = ((extraData || {})._errors || {}).pipeimobRequired || 'leitura nao executada';
		return {
			success: false,
			reason: 'Nao foi possivel ler a configuracao PIPEIMOB_REQUIRED_FIELDS (' + motivo + '). Tente de novo ou avise o administrador.',
		};
	}
	var bruto = settings.length ? settings[0].value : null;
	if (vazio(bruto)) {
		return { success: true }; // gate desligado: tenant sem a Setting
	}

	// Com o gate ligado, leitura do comprador/imovel que falhou barra dizendo isso -- acusar "falta CPF" seria mentir
	// sobre a causa. Vem DEPOIS do "Setting ausente": tenant sem PipeImob nao pode ser barrado por isso.
	var erros = (extraData || {})._errors || {};
	if (erros.pipeimobContact) {
		return { success: false, reason: 'Nao foi possivel ler os dados do comprador (' + erros.pipeimobContact + '). Tente de novo ou avise o administrador.' };
	}
	if (erros.pipeimobProduct || erros.pipeimobProductBroker) {
		return {
			success: false,
			reason: 'Nao foi possivel ler os dados do imovel (' + (erros.pipeimobProduct || erros.pipeimobProductBroker) + '). Tente de novo ou avise o administrador.',
		};
	}

	var requeridos;
	try {
		requeridos = JSON.parse(bruto);
	} catch (e) {
		return {
			success: false,
			reason: 'A Setting PIPEIMOB_REQUIRED_FIELDS nao e um JSON valido; corrija-a antes de marcar Proposta aceita.',
		};
	}
	if (
		!Array.isArray(requeridos) ||
		requeridos.some(function (x) {
			return typeof x !== 'string';
		})
	) {
		return {
			success: false,
			reason: 'A Setting PIPEIMOB_REQUIRED_FIELDS deve ser uma lista JSON de textos "caminho|Rotulo"; corrija-a antes de marcar Proposta aceita.',
		};
	}

	var contexto = {
		opportunity: data,
		contact: ((extraData || {}).pipeimobContact || [])[0] || {},
		// `product` (Imovel) existe em overlays como o da Auxiliadora; na base o lookup e `productBroker`
		product: ((extraData || {}).pipeimobProduct || [])[0] || ((extraData || {}).pipeimobProductBroker || [])[0] || {},
	};

	var faltando = [];
	for (var i = 0; i < requeridos.length; i++) {
		var item = String(requeridos[i]);
		var sep = item.indexOf('|');
		var caminho = sep >= 0 ? item.slice(0, sep).trim() : item.trim();
		var rotulo = sep >= 0 ? item.slice(sep + 1).trim() : caminho;
		if (!caminho) continue;
		if (vazio(ler(contexto, caminho))) faltando.push(rotulo);
	}

	if (faltando.length) {
		return {
			success: false,
			reason: 'Para marcar Proposta aceita falta preencher: ' + faltando.join(', ') + '. O TRM precisa desses dados para abrir a transacao.',
		};
	}
	return { success: true };
} catch (e) {
	console.log(e);
	return { success: false, reason: 'Houve um erro inesperado: ' + e.message };
}
