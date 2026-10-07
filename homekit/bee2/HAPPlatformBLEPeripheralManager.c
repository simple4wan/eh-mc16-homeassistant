#include "HAPPlatformBLEPeripheralManager+Init.h"

#include <string.h>
#include <gap.h>
#include <gap_adv.h>
#include <gap_conn_le.h>
#include <gap_le.h>

#define EH_HAP_DEFAULT_FIRST_HANDLE 0x0100

static HAPPlatformBLEPeripheralManagerRef gManager;

static EH_HAP_BLE_Service* CurrentService(HAPPlatformBLEPeripheralManagerRef m) {
    if (!m || m->currentService < 0 || (uint8_t)m->currentService >= m->numServices) {
        return NULL;
    }
    return &m->services[(uint8_t)m->currentService];
}

static uint8_t CharProperties(HAPPlatformBLEPeripheralManagerCharacteristicProperties p) {
    uint8_t v = 0;
    if (p.read) v |= GATT_CHAR_PROP_READ;
    if (p.writeWithoutResponse) v |= GATT_CHAR_PROP_WRITE_NO_RSP;
    if (p.write) v |= GATT_CHAR_PROP_WRITE;
    if (p.notify) v |= GATT_CHAR_PROP_NOTIFY;
    if (p.indicate) v |= GATT_CHAR_PROP_INDICATE;
    return v;
}

static uint32_t CharPermissions(HAPPlatformBLEPeripheralManagerCharacteristicProperties p) {
    uint32_t v = 0;
    if (p.read) v |= GATT_PERM_READ;
    if (p.write || p.writeWithoutResponse) v |= GATT_PERM_WRITE;
    return v;
}

static uint16_t AbsoluteHandle(EH_HAP_BLE_Service* s, uint16_t attribIndex) {
    return (uint16_t)(s->startHandle + attribIndex);
}

static EH_HAP_BLE_Service* FindServiceById(T_SERVER_ID serviceId) {
    if (!gManager) return NULL;
    for (uint8_t i = 0; i < gManager->numServices; i++) {
        if (gManager->services[i].registered && gManager->services[i].serviceId == serviceId) {
            return &gManager->services[i];
        }
    }
    return NULL;
}

static T_APP_RESULT Bee2Read(
        uint8_t connId,
        T_SERVER_ID serviceId,
        uint16_t attribIndex,
        uint16_t offset,
        uint16_t* length,
        uint8_t** value) {
    static uint8_t readBuffer[kHAPPlatformBLEPeripheralManager_MaxAttributeBytes];
    EH_HAP_BLE_Service* s = FindServiceById(serviceId);
    if (!s || attribIndex >= s->numAttrs || !gManager) return APP_RESULT_ATTR_NOT_FOUND;

    if (s->constLengths[attribIndex]) {
        uint16_t n = s->constLengths[attribIndex];
        if (offset > n) return APP_RESULT_INVALID_OFFSET;
        *value = &s->constValues[attribIndex][offset];
        *length = (uint16_t)(n - offset);
        return APP_RESULT_SUCCESS;
    }

    if (!gManager->delegate.handleReadRequest) return APP_RESULT_ATTR_NOT_FOUND;
    size_t n = 0;
    HAPError err = gManager->delegate.handleReadRequest(
            gManager,
            connId,
            AbsoluteHandle(s, attribIndex),
            readBuffer,
            sizeof readBuffer,
            &n,
            gManager->delegate.context);
    if (err || n > UINT16_MAX || offset > n) return APP_RESULT_APP_ERR;
    *value = &readBuffer[offset];
    *length = (uint16_t)(n - offset);
    return APP_RESULT_SUCCESS;
}

static T_APP_RESULT Bee2Write(
        uint8_t connId,
        T_SERVER_ID serviceId,
        uint16_t attribIndex,
        T_WRITE_TYPE writeType,
        uint16_t length,
        uint8_t* value,
        P_FUN_WRITE_IND_POST_PROC* postProc) {
    (void) writeType;
    (void) postProc;
    EH_HAP_BLE_Service* s = FindServiceById(serviceId);
    if (!s || attribIndex >= s->numAttrs || !gManager || !gManager->delegate.handleWriteRequest) {
        return APP_RESULT_ATTR_NOT_FOUND;
    }
    HAPError err = gManager->delegate.handleWriteRequest(
            gManager,
            connId,
            AbsoluteHandle(s, attribIndex),
            value,
            length,
            gManager->delegate.context);
    return err ? APP_RESULT_APP_ERR : APP_RESULT_SUCCESS;
}

static void Bee2CCCD(
        uint8_t connId,
        T_SERVER_ID serviceId,
        uint16_t attribIndex,
        uint16_t cccBits) {
    EH_HAP_BLE_Service* s = FindServiceById(serviceId);
    if (!s || !gManager || !gManager->delegate.handleWriteRequest) return;

    uint8_t bytes[2] = { LO_WORD(cccBits), HI_WORD(cccBits) };
    (void) gManager->delegate.handleWriteRequest(
            gManager,
            connId,
            AbsoluteHandle(s, attribIndex),
            bytes,
            sizeof bytes,
            gManager->delegate.context);
}

static const T_FUN_GATT_SERVICE_CBS kBee2Callbacks = {
    Bee2Read,
    Bee2Write,
    Bee2CCCD
};

void HAPPlatformBLEPeripheralManagerCreate(
        HAPPlatformBLEPeripheralManagerRef m,
        const HAPPlatformBLEPeripheralManagerOptions* options) {
    memset(m, 0, sizeof *m);
    m->currentService = -1;
    m->nextHandle = options && options->firstHandle ? options->firstHandle : EH_HAP_DEFAULT_FIRST_HANDLE;
    gManager = m;
}

void HAPPlatformBLEPeripheralManagerSetDelegate(
        HAPPlatformBLEPeripheralManagerRef m,
        const HAPPlatformBLEPeripheralManagerDelegate* delegate) {
    if (delegate) m->delegate = *delegate;
    else memset(&m->delegate, 0, sizeof m->delegate);
}

void HAPPlatformBLEPeripheralManagerSetDeviceAddress(
        HAPPlatformBLEPeripheralManagerRef m,
        const HAPPlatformBLEPeripheralManagerDeviceAddress* address) {
    m->deviceAddress = *address;
    m->isDeviceAddressSet = true;
    /* HomeKit supplies a random-static address. Bee2 accepts it directly. */
    (void) le_set_rand_addr(m->deviceAddress.bytes);
}

void HAPPlatformBLEPeripheralManagerSetDeviceName(
        HAPPlatformBLEPeripheralManagerRef m,
        const char* name) {
    size_t n = strlen(name);
    if (n >= sizeof m->deviceName) n = sizeof m->deviceName - 1;
    memcpy(m->deviceName, name, n);
    m->deviceName[n] = 0;
    le_set_gap_param(GAP_PARAM_DEVICE_NAME, (uint8_t)n + 1, m->deviceName);
}

void HAPPlatformBLEPeripheralManagerRemoveAllServices(HAPPlatformBLEPeripheralManagerRef m) {
    /* Bee2's legacy profile server does not support unregistering services at runtime.
       HAP only calls this while rebuilding the database before normal operation.
       Reinitialize the builder; a full server restart is performed by the application. */
    memset(m->services, 0, sizeof m->services);
    m->numServices = 0;
    m->currentService = -1;
    m->nextHandle = EH_HAP_DEFAULT_FIRST_HANDLE;
    m->didPublishAttributes = false;
}

HAPError HAPPlatformBLEPeripheralManagerAddService(
        HAPPlatformBLEPeripheralManagerRef m,
        const HAPPlatformBLEPeripheralManagerUUID* type,
        bool isPrimary) {
    if (m->numServices >= EH_HAP_MAX_SERVICES) return kHAPError_OutOfResources;

    EH_HAP_BLE_Service* s = &m->services[m->numServices];
    memset(s, 0, sizeof *s);
    s->startHandle = m->nextHandle;

    T_ATTRIB_APPL* a = &s->attrs[0];
    a->flags = ATTRIB_FLAG_VOID | ATTRIB_FLAG_LE;
    a->type_value[0] = LO_WORD(isPrimary ? GATT_UUID_PRIMARY_SERVICE : GATT_UUID_SECONDARY_SERVICE);
    a->type_value[1] = HI_WORD(isPrimary ? GATT_UUID_PRIMARY_SERVICE : GATT_UUID_SECONDARY_SERVICE);
    memcpy(s->uuidValues[0], type->bytes, 16);
    a->value_len = UUID_128BIT_SIZE;
    a->p_value_context = s->uuidValues[0];
    a->permissions = GATT_PERM_READ;
    s->numAttrs = 1;

    m->currentService = (int8_t)m->numServices;
    m->numServices++;
    return kHAPError_None;
}

HAPError HAPPlatformBLEPeripheralManagerAddCharacteristic(
        HAPPlatformBLEPeripheralManagerRef m,
        const HAPPlatformBLEPeripheralManagerUUID* type,
        HAPPlatformBLEPeripheralManagerCharacteristicProperties properties,
        const void* constBytes,
        size_t constNumBytes,
        HAPPlatformBLEPeripheralManagerAttributeHandle* valueHandle,
        HAPPlatformBLEPeripheralManagerAttributeHandle* cccDescriptorHandle) {
    EH_HAP_BLE_Service* s = CurrentService(m);
    uint16_t needed = (uint16_t)(2 + ((properties.notify || properties.indicate) ? 1 : 0));
    if (!s || s->numAttrs + needed > EH_HAP_MAX_ATTRS_PER_SERVICE) return kHAPError_OutOfResources;
    if (constNumBytes > EH_HAP_MAX_CONST_BYTES) return kHAPError_OutOfResources;

    uint16_t d = s->numAttrs++;
    T_ATTRIB_APPL* decl = &s->attrs[d];
    decl->flags = ATTRIB_FLAG_VALUE_INCL;
    decl->type_value[0] = LO_WORD(GATT_UUID_CHARACTERISTIC);
    decl->type_value[1] = HI_WORD(GATT_UUID_CHARACTERISTIC);
    decl->type_value[2] = CharProperties(properties);
    decl->value_len = 1;
    decl->permissions = GATT_PERM_READ;

    uint16_t v = s->numAttrs++;
    T_ATTRIB_APPL* val = &s->attrs[v];
    val->flags = ATTRIB_FLAG_VALUE_APPL | ATTRIB_FLAG_UUID_128BIT;
    memcpy(val->type_value, type->bytes, 16);
    val->value_len = 0;
    val->permissions = CharPermissions(properties);
    if (constBytes && constNumBytes) {
        memcpy(s->constValues[v], constBytes, constNumBytes);
        s->constLengths[v] = (uint16_t)constNumBytes;
    }
    *valueHandle = AbsoluteHandle(s, v);

    if (properties.notify || properties.indicate) {
        uint16_t c = s->numAttrs++;
        T_ATTRIB_APPL* cccd = &s->attrs[c];
        cccd->flags = ATTRIB_FLAG_VALUE_INCL | ATTRIB_FLAG_CCCD_APPL;
        cccd->type_value[0] = LO_WORD(GATT_UUID_CHAR_CLIENT_CONFIG);
        cccd->type_value[1] = HI_WORD(GATT_UUID_CHAR_CLIENT_CONFIG);
        cccd->type_value[2] = LO_WORD(GATT_CLIENT_CHAR_CONFIG_DEFAULT);
        cccd->type_value[3] = HI_WORD(GATT_CLIENT_CHAR_CONFIG_DEFAULT);
        cccd->value_len = 2;
        cccd->permissions = GATT_PERM_READ | GATT_PERM_WRITE;
        if (cccDescriptorHandle) *cccDescriptorHandle = AbsoluteHandle(s, c);
    } else if (cccDescriptorHandle) {
        *cccDescriptorHandle = 0;
    }

    return kHAPError_None;
}

HAPError HAPPlatformBLEPeripheralManagerAddDescriptor(
        HAPPlatformBLEPeripheralManagerRef m,
        const HAPPlatformBLEPeripheralManagerUUID* type,
        HAPPlatformBLEPeripheralManagerDescriptorProperties properties,
        const void* constBytes,
        size_t constNumBytes,
        HAPPlatformBLEPeripheralManagerAttributeHandle* descriptorHandle) {
    EH_HAP_BLE_Service* s = CurrentService(m);
    if (!s || s->numAttrs >= EH_HAP_MAX_ATTRS_PER_SERVICE || constNumBytes > EH_HAP_MAX_CONST_BYTES) {
        return kHAPError_OutOfResources;
    }

    uint16_t i = s->numAttrs++;
    T_ATTRIB_APPL* a = &s->attrs[i];
    a->flags = ATTRIB_FLAG_VALUE_APPL | ATTRIB_FLAG_UUID_128BIT;
    memcpy(a->type_value, type->bytes, 16);
    a->value_len = 0;
    a->permissions = (properties.read ? GATT_PERM_READ : 0) | (properties.write ? GATT_PERM_WRITE : 0);
    if (constBytes && constNumBytes) {
        memcpy(s->constValues[i], constBytes, constNumBytes);
        s->constLengths[i] = (uint16_t)constNumBytes;
    }
    *descriptorHandle = AbsoluteHandle(s, i);
    return kHAPError_None;
}

void HAPPlatformBLEPeripheralManagerPublishServices(HAPPlatformBLEPeripheralManagerRef m) {
    for (uint8_t i = 0; i < m->numServices; i++) {
        EH_HAP_BLE_Service* s = &m->services[i];
        if (!server_add_service_by_start_handle(
                    &s->serviceId,
                    (uint8_t*)s->attrs,
                    (uint16_t)(s->numAttrs * sizeof(T_ATTRIB_APPL)),
                    kBee2Callbacks,
                    s->startHandle)) {
            continue;
        }
        s->registered = true;
        m->nextHandle = (uint16_t)(s->startHandle + s->numAttrs);
    }
    m->didPublishAttributes = true;
}

void HAPPlatformBLEPeripheralManagerStartAdvertising(
        HAPPlatformBLEPeripheralManagerRef m,
        HAPBLEAdvertisingInterval advertisingInterval,
        const void* advertisingBytes,
        size_t numAdvertisingBytes,
        const void* scanResponseBytes,
        size_t numScanResponseBytes) {
    if (numAdvertisingBytes > 31 || numScanResponseBytes > 31) return;
    m->advertisingRequested = true;
    memcpy(m->advertisingBytes, advertisingBytes, numAdvertisingBytes);
    m->numAdvertisingBytes = (uint8_t)numAdvertisingBytes;
    if (scanResponseBytes && numScanResponseBytes) {
        memcpy(m->scanResponseBytes, scanResponseBytes, numScanResponseBytes);
    }
    m->numScanResponseBytes = (uint8_t)numScanResponseBytes;

    /* HAPBLEAdvertisingInterval uses Bluetooth 0.625 ms units, same as Bee2. */
    uint16_t interval = (uint16_t)advertisingInterval;
    le_adv_set_param(GAP_PARAM_ADV_EVENT_TYPE, sizeof(uint8_t), &(uint8_t){ GAP_ADTYPE_ADV_IND });
    le_adv_set_param(GAP_PARAM_ADV_INTERVAL_MIN, sizeof interval, &interval);
    le_adv_set_param(GAP_PARAM_ADV_INTERVAL_MAX, sizeof interval, &interval);
    le_adv_set_param(GAP_PARAM_ADV_DATA, m->numAdvertisingBytes, m->advertisingBytes);
    le_adv_set_param(GAP_PARAM_SCAN_RSP_DATA, m->numScanResponseBytes, m->scanResponseBytes);
    if (m->stackReady) {
        (void) le_adv_stop();
        (void) le_adv_update_param();
        (void) le_adv_start();
        m->advertising = true;
    }
}

void HAPPlatformBLEPeripheralManagerStopAdvertising(HAPPlatformBLEPeripheralManagerRef m) {
    m->advertisingRequested = false;
    if (m->stackReady) {
        (void) le_adv_stop();
    }
    m->advertising = false;
}

void HAPPlatformBLEPeripheralManagerCancelCentralConnection(
        HAPPlatformBLEPeripheralManagerRef m,
        HAPPlatformBLEPeripheralManagerConnectionHandle connectionHandle) {
    (void)m;
    /* HAP uses one BLE peripheral connection. Bee2 conn_id and HCI handle are
       translated by the application GAP bridge; disconnect hook is added there. */
    (void)connectionHandle;
}

HAPError HAPPlatformBLEPeripheralManagerSendHandleValueIndication(
        HAPPlatformBLEPeripheralManagerRef m,
        HAPPlatformBLEPeripheralManagerConnectionHandle connectionHandle,
        HAPPlatformBLEPeripheralManagerAttributeHandle valueHandle,
        const void* bytes,
        size_t numBytes) {
    if (!m->connected || connectionHandle != m->connId || numBytes > UINT16_MAX) {
        return kHAPError_InvalidState;
    }
    for (uint8_t i = 0; i < m->numServices; i++) {
        EH_HAP_BLE_Service* s = &m->services[i];
        if (valueHandle >= s->startHandle && valueHandle < s->startHandle + s->numAttrs) {
            uint16_t idx = (uint16_t)(valueHandle - s->startHandle);
            if (!server_send_data(
                        m->connId,
                        s->serviceId,
                        idx,
                        (uint8_t*)bytes,
                        (uint16_t)numBytes,
                        GATT_PDU_TYPE_INDICATION)) {
                return kHAPError_OutOfResources;
            }
            return kHAPError_None;
        }
    }
    return kHAPError_InvalidState;
}

void EH_HAP_BLE_StackReady(HAPPlatformBLEPeripheralManagerRef m) {
    m->stackReady = true;
    if (m->advertisingRequested) {
        (void) le_adv_update_param();
        (void) le_adv_start();
        m->advertising = true;
    }
}

void EH_HAP_BLE_DidConnect(HAPPlatformBLEPeripheralManagerRef m, uint8_t connId) {
    m->connected = true;
    m->connId = connId;
    if (m->delegate.handleConnectedCentral) {
        m->delegate.handleConnectedCentral(m, connId, m->delegate.context);
    }
}

void EH_HAP_BLE_DidDisconnect(HAPPlatformBLEPeripheralManagerRef m, uint8_t connId) {
    if (m->delegate.handleDisconnectedCentral) {
        m->delegate.handleDisconnectedCentral(m, connId, m->delegate.context);
    }
    m->connected = false;
}

void EH_HAP_BLE_DidSendData(HAPPlatformBLEPeripheralManagerRef m, uint8_t connId) {
    if (m->delegate.handleReadyToUpdateSubscribers) {
        m->delegate.handleReadyToUpdateSubscribers(m, connId, m->delegate.context);
    }
}
