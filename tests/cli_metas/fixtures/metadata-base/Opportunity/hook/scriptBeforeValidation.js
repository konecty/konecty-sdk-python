var ret = {};
var request = extraData != null && extraData.request != null ? extraData.request : {};
// rentalDiscardReason: as quatro saídas sem tentativa da locação só existem nele (#5502).
// rentalLossReason não entra: o adormecido volta ao funil pela retomada.
if ((data.discardReason != null || data.withdrawalReason != null || data.rentalDiscardReason != null) && !('status' in request)) {
	ret.status = 'Closed';
}
return ret;
