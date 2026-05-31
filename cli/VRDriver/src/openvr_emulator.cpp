#include "openvr.h"
#include <cstring>
#include <iostream>
#include <fstream>
#include <windows.h>
#include <d3d11.h>

struct SharedFrame {
    uint32_t sequenceNumber;
    uint32_t width;
    uint32_t height;
    uint32_t format;
};

#pragma pack(push, 1)
struct SharedHands {
    float leftTransform[16];
    float rightTransform[16];
    uint8_t leftPinch;
    uint8_t rightPinch;
};
#pragma pack(pop)

static HANDLE hMapFile = NULL;
static void* pBuf = NULL;
static SharedFrame* pHeader = NULL;
static uint8_t* pPixelData = NULL;
static SharedHands* pSharedHands = NULL;
static uint32_t frameSeq = 1;
static ID3D11Texture2D* pStagingTexture = NULL;

static void InitSharedMemory() {
    if (hMapFile) return;
    
    const int mapSize = 16 + 1920 * 1080 * 4 + 130;
    
    HANDLE hFile = CreateFileA("C:\\vr_shared_frame.dat", GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile != INVALID_HANDLE_VALUE) {
        LARGE_INTEGER fsize;
        GetFileSizeEx(hFile, &fsize);
        if (fsize.QuadPart < mapSize) {
            SetFilePointer(hFile, mapSize - 1, NULL, FILE_BEGIN);
            DWORD written;
            WriteFile(hFile, "", 1, &written, NULL);
        }
        hMapFile = CreateFileMappingA(hFile, NULL, PAGE_READWRITE, 0, mapSize, NULL);
        if (hMapFile) {
            pBuf = MapViewOfFile(hMapFile, FILE_MAP_ALL_ACCESS, 0, 0, mapSize);
            if (pBuf) {
                pHeader = (SharedFrame*)pBuf;
                pPixelData = (uint8_t*)pBuf + sizeof(SharedFrame);
                pSharedHands = (SharedHands*)((uint8_t*)pBuf + 16 + 1920 * 1080 * 4);
                memset(pSharedHands, 0, sizeof(SharedHands));
            }
        }
    }
}

using namespace vr;

class UniversalMock {
public:
    virtual void* Dummy0() { return nullptr; }
    virtual void* Dummy1() { return nullptr; }
    virtual void* Dummy2() { return nullptr; }
    virtual void* Dummy3() { return nullptr; }
    virtual void* Dummy4() { return nullptr; }
    virtual void* Dummy5() { return nullptr; }
    virtual void* Dummy6() { return nullptr; }
    virtual void* Dummy7() { return nullptr; }
    virtual void* Dummy8() { return nullptr; }
    virtual void* Dummy9() { return nullptr; }
    virtual void* Dummy10() { return nullptr; }
    virtual void* Dummy11() { return nullptr; }
    virtual void* Dummy12() { return nullptr; }
    virtual void* Dummy13() { return nullptr; }
    virtual void* Dummy14() { return nullptr; }
    virtual void* Dummy15() { return nullptr; }
    virtual void* Dummy16() { return nullptr; }
    virtual void* Dummy17() { return nullptr; }
    virtual void* Dummy18() { return nullptr; }
    virtual void* Dummy19() { return nullptr; }
    virtual void* Dummy20() { return nullptr; }
    virtual void* Dummy21() { return nullptr; }
    virtual void* Dummy22() { return nullptr; }
    virtual void* Dummy23() { return nullptr; }
    virtual void* Dummy24() { return nullptr; }
    virtual void* Dummy25() { return nullptr; }
    virtual void* Dummy26() { return nullptr; }
    virtual void* Dummy27() { return nullptr; }
    virtual void* Dummy28() { return nullptr; }
    virtual void* Dummy29() { return nullptr; }
    virtual void* Dummy30() { return nullptr; }
    virtual void* Dummy31() { return nullptr; }
    virtual void* Dummy32() { return nullptr; }
    virtual void* Dummy33() { return nullptr; }
    virtual void* Dummy34() { return nullptr; }
    virtual void* Dummy35() { return nullptr; }
    virtual void* Dummy36() { return nullptr; }
    virtual void* Dummy37() { return nullptr; }
    virtual void* Dummy38() { return nullptr; }
    virtual void* Dummy39() { return nullptr; }
    virtual void* Dummy40() { return nullptr; }
    virtual void* Dummy41() { return nullptr; }
    virtual void* Dummy42() { return nullptr; }
    virtual void* Dummy43() { return nullptr; }
    virtual void* Dummy44() { return nullptr; }
    virtual void* Dummy45() { return nullptr; }
    virtual void* Dummy46() { return nullptr; }
    virtual void* Dummy47() { return nullptr; }
    virtual void* Dummy48() { return nullptr; }
    virtual void* Dummy49() { return nullptr; }
    virtual void* Dummy50() { return nullptr; }
    virtual void* Dummy51() { return nullptr; }
    virtual void* Dummy52() { return nullptr; }
    virtual void* Dummy53() { return nullptr; }
    virtual void* Dummy54() { return nullptr; }
    virtual void* Dummy55() { return nullptr; }
    virtual void* Dummy56() { return nullptr; }
    virtual void* Dummy57() { return nullptr; }
    virtual void* Dummy58() { return nullptr; }
    virtual void* Dummy59() { return nullptr; }
    virtual void* Dummy60() { return nullptr; }
    virtual void* Dummy61() { return nullptr; }
    virtual void* Dummy62() { return nullptr; }
    virtual void* Dummy63() { return nullptr; }
    virtual void* Dummy64() { return nullptr; }
    virtual void* Dummy65() { return nullptr; }
    virtual void* Dummy66() { return nullptr; }
    virtual void* Dummy67() { return nullptr; }
    virtual void* Dummy68() { return nullptr; }
    virtual void* Dummy69() { return nullptr; }
    virtual void* Dummy70() { return nullptr; }
    virtual void* Dummy71() { return nullptr; }
    virtual void* Dummy72() { return nullptr; }
    virtual void* Dummy73() { return nullptr; }
    virtual void* Dummy74() { return nullptr; }
    virtual void* Dummy75() { return nullptr; }
    virtual void* Dummy76() { return nullptr; }
    virtual void* Dummy77() { return nullptr; }
    virtual void* Dummy78() { return nullptr; }
    virtual void* Dummy79() { return nullptr; }
    virtual void* Dummy80() { return nullptr; }
    virtual void* Dummy81() { return nullptr; }
    virtual void* Dummy82() { return nullptr; }
    virtual void* Dummy83() { return nullptr; }
    virtual void* Dummy84() { return nullptr; }
    virtual void* Dummy85() { return nullptr; }
    virtual void* Dummy86() { return nullptr; }
    virtual void* Dummy87() { return nullptr; }
    virtual void* Dummy88() { return nullptr; }
    virtual void* Dummy89() { return nullptr; }
    virtual void* Dummy90() { return nullptr; }
    virtual void* Dummy91() { return nullptr; }
    virtual void* Dummy92() { return nullptr; }
    virtual void* Dummy93() { return nullptr; }
    virtual void* Dummy94() { return nullptr; }
    virtual void* Dummy95() { return nullptr; }
    virtual void* Dummy96() { return nullptr; }
    virtual void* Dummy97() { return nullptr; }
    virtual void* Dummy98() { return nullptr; }
    virtual void* Dummy99() { return nullptr; }
};
UniversalMock g_universalMock;

class Mock_IVRSystem : public vr::IVRSystem {
public:
    virtual void GetRecommendedRenderTargetSize(uint32_t *pnWidth, uint32_t *pnHeight) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetRecommendedRenderTargetSize\n"); fclose(_f); }
        if(pnWidth) *pnWidth = 1920;
        if(pnHeight) *pnHeight = 1080;
    }
    virtual void GetProjectionMatrix(HmdMatrix44_t *pRet, EVREye eEye, float fNearZ, float fFarZ) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetProjectionMatrix\n"); fclose(_f); }
        if(pRet) { memset(pRet, 0, sizeof(*pRet)); }
        if(pRet) { memset(pRet, 0, sizeof(*pRet)); pRet->m[0][0] = 1; pRet->m[1][1] = 1; pRet->m[2][2] = 1; pRet->m[3][3] = 1; }
    }
    virtual void GetProjectionRaw(EVREye eEye, float *pfLeft, float *pfRight, float *pfTop, float *pfBottom) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetProjectionRaw\n"); fclose(_f); }
        if(pfLeft) *pfLeft = -1.0f; if(pfRight) *pfRight = 1.0f; if(pfTop) *pfTop = -1.0f; if(pfBottom) *pfBottom = 1.0f;
    }
    virtual bool ComputeDistortion(EVREye eEye, float fU, float fV, DistortionCoordinates_t *pDistortionCoordinates) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::ComputeDistortion\n"); fclose(_f); }
        if(pDistortionCoordinates) { memset(pDistortionCoordinates, 0, sizeof(*pDistortionCoordinates)); }
        return true;
    }
    virtual void GetEyeToHeadTransform(HmdMatrix34_t *pRet, EVREye eEye) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetEyeToHeadTransform\n"); fclose(_f); }
        if(pRet) { memset(pRet, 0, sizeof(*pRet)); }
        if(pRet) { memset(pRet, 0, sizeof(*pRet)); pRet->m[0][0] = 1; pRet->m[1][1] = 1; pRet->m[2][2] = 1; }
    }
    virtual bool GetTimeSinceLastVsync(float *pfSecondsSinceLastVsync, uint64_t *pulFrameCounter) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetTimeSinceLastVsync\n"); fclose(_f); }
        static uint64_t frame = 0; frame++;
        if(pfSecondsSinceLastVsync) *pfSecondsSinceLastVsync = 0.011f;
        if(pulFrameCounter) *pulFrameCounter = frame;
        return true;
    }
    virtual int32_t GetD3D9AdapterIndex() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetD3D9AdapterIndex\n"); fclose(_f); }
        return (int32_t)0;
    }
    virtual void GetDXGIOutputInfo(int32_t *pnAdapterIndex) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetDXGIOutputInfo\n"); fclose(_f); }
        if(pnAdapterIndex) *pnAdapterIndex = 0;
    }
    virtual void GetOutputDevice(uint64_t *pnDevice, ETextureType textureType, VkInstance_T *pInstance = nullptr) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetOutputDevice\n"); fclose(_f); }
        if(pnDevice) *pnDevice = 0;
    }
    virtual bool IsDisplayOnDesktop() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::IsDisplayOnDesktop\n"); fclose(_f); }
        return false;
    }
    virtual bool SetDisplayVisibility(bool bIsVisibleOnDesktop) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::SetDisplayVisibility\n"); fclose(_f); }
        return false;
    }
    virtual void GetDeviceToAbsoluteTrackingPose(ETrackingUniverseOrigin eOrigin, float fPredictedSecondsToPhotonsFromNow, VR_ARRAY_COUNT(unTrackedDevicePoseArrayCount) TrackedDevicePose_t *pTrackedDevicePoseArray, uint32_t unTrackedDevicePoseArrayCount) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetDeviceToAbsoluteTrackingPose\n"); fclose(_f); }
        if(pTrackedDevicePoseArray && unTrackedDevicePoseArrayCount > 0) { memset(pTrackedDevicePoseArray, 0, sizeof(vr::TrackedDevicePose_t) * unTrackedDevicePoseArrayCount); for(uint32_t i=0; i<3 && i<unTrackedDevicePoseArrayCount; ++i) { pTrackedDevicePoseArray[i].bPoseIsValid = true; pTrackedDevicePoseArray[i].bDeviceIsConnected = true; pTrackedDevicePoseArray[i].eTrackingResult = vr::TrackingResult_Running_OK; pTrackedDevicePoseArray[i].mDeviceToAbsoluteTracking.m[0][0] = 1; pTrackedDevicePoseArray[i].mDeviceToAbsoluteTracking.m[1][1] = 1; pTrackedDevicePoseArray[i].mDeviceToAbsoluteTracking.m[2][2] = 1; } }
    }
    virtual void ResetSeatedZeroPose() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::ResetSeatedZeroPose\n"); fclose(_f); }
    }
    virtual void GetSeatedZeroPoseToStandingAbsoluteTrackingPose(HmdMatrix34_t *pRet) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetSeatedZeroPoseToStandingAbsoluteTrackingPose\n"); fclose(_f); }
        if(pRet) { memset(pRet, 0, sizeof(*pRet)); }
        if(pRet) { memset(pRet, 0, sizeof(*pRet)); }
        if(pRet) { ((vr::HmdMatrix34_t*)pRet)->m[0][0] = 1; ((vr::HmdMatrix34_t*)pRet)->m[1][1] = 1; ((vr::HmdMatrix34_t*)pRet)->m[2][2] = 1; }
    }
    virtual void GetRawZeroPoseToStandingAbsoluteTrackingPose(HmdMatrix34_t *pRet) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetRawZeroPoseToStandingAbsoluteTrackingPose\n"); fclose(_f); }
        if(pRet) { memset(pRet, 0, sizeof(*pRet)); }
        if(pRet) { memset(pRet, 0, sizeof(*pRet)); }
        if(pRet) { ((vr::HmdMatrix34_t*)pRet)->m[0][0] = 1; ((vr::HmdMatrix34_t*)pRet)->m[1][1] = 1; ((vr::HmdMatrix34_t*)pRet)->m[2][2] = 1; }
    }
    virtual uint32_t GetSortedTrackedDeviceIndicesOfClass(ETrackedDeviceClass eTrackedDeviceClass, VR_ARRAY_COUNT(unTrackedDeviceIndexArrayCount) vr::TrackedDeviceIndex_t *punTrackedDeviceIndexArray, uint32_t unTrackedDeviceIndexArrayCount, vr::TrackedDeviceIndex_t unRelativeToTrackedDeviceIndex = k_unTrackedDeviceIndex_Hmd) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetSortedTrackedDeviceIndicesOfClass\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual EDeviceActivityLevel GetTrackedDeviceActivityLevel(vr::TrackedDeviceIndex_t unDeviceId) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetTrackedDeviceActivityLevel\n"); fclose(_f); }
        return vr::k_EDeviceActivityLevel_UserInteraction;
    }
    virtual void ApplyTransform(TrackedDevicePose_t *pOutputPose, const TrackedDevicePose_t *pTrackedDevicePose, const HmdMatrix34_t *pTransform) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::ApplyTransform\n"); fclose(_f); }
    }
    virtual vr::TrackedDeviceIndex_t GetTrackedDeviceIndexForControllerRole(vr::ETrackedControllerRole unDeviceType) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetTrackedDeviceIndexForControllerRole\n"); fclose(_f); }
        return (vr::TrackedDeviceIndex_t)0;
    }
    virtual vr::ETrackedControllerRole GetControllerRoleForTrackedDeviceIndex(vr::TrackedDeviceIndex_t unDeviceIndex) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetControllerRoleForTrackedDeviceIndex\n"); fclose(_f); }
        if (unDeviceIndex == 1) return vr::TrackedControllerRole_LeftHand;
        if (unDeviceIndex == 2) return vr::TrackedControllerRole_RightHand;
        return vr::TrackedControllerRole_Invalid;
    }
    virtual ETrackedDeviceClass GetTrackedDeviceClass(vr::TrackedDeviceIndex_t unDeviceIndex) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetTrackedDeviceClass\n"); fclose(_f); }
        if(unDeviceIndex == 0) return vr::TrackedDeviceClass_HMD;
        if(unDeviceIndex == 1 || unDeviceIndex == 2) return vr::TrackedDeviceClass_Controller;
        return vr::TrackedDeviceClass_Invalid;
    }
    virtual bool IsTrackedDeviceConnected(vr::TrackedDeviceIndex_t unDeviceIndex) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::IsTrackedDeviceConnected\n"); fclose(_f); }
        if(unDeviceIndex == 0 || unDeviceIndex == 1 || unDeviceIndex == 2) return true;
        return false;
    }
    virtual bool GetBoolTrackedDeviceProperty(vr::TrackedDeviceIndex_t unDeviceIndex, ETrackedDeviceProperty prop, ETrackedPropertyError *pError = 0L) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetBoolTrackedDeviceProperty\n"); fclose(_f); }
        return false;
    }
    virtual float GetFloatTrackedDeviceProperty(vr::TrackedDeviceIndex_t unDeviceIndex, ETrackedDeviceProperty prop, ETrackedPropertyError *pError = 0L) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetFloatTrackedDeviceProperty\n"); fclose(_f); }
        if(pError) *pError = vr::TrackedProp_Success;
        if(prop == vr::Prop_DisplayFrequency_Float) return 90.0f;
        return 0.0f;
    }
    virtual int32_t GetInt32TrackedDeviceProperty(vr::TrackedDeviceIndex_t unDeviceIndex, ETrackedDeviceProperty prop, ETrackedPropertyError *pError = 0L) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetInt32TrackedDeviceProperty\n"); fclose(_f); }
        if(pError) *pError = vr::TrackedProp_Success;
        if(prop == vr::Prop_DeviceClass_Int32) { if(unDeviceIndex == 0) return vr::TrackedDeviceClass_HMD; if(unDeviceIndex == 1 || unDeviceIndex == 2) return vr::TrackedDeviceClass_Controller; }
        if(prop == vr::Prop_ControllerRoleHint_Int32) { if(unDeviceIndex == 1) return vr::TrackedControllerRole_LeftHand; if(unDeviceIndex == 2) return vr::TrackedControllerRole_RightHand; }
        if(prop == vr::Prop_Axis0Type_Int32 || prop == vr::Prop_Axis1Type_Int32) return vr::k_eControllerAxis_TrackPad;
        return 0;
    }
    virtual uint64_t GetUint64TrackedDeviceProperty(vr::TrackedDeviceIndex_t unDeviceIndex, ETrackedDeviceProperty prop, ETrackedPropertyError *pError = 0L) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetUint64TrackedDeviceProperty\n"); fclose(_f); }
        if(pError) *pError = vr::TrackedProp_Success;
        if(prop == vr::Prop_CurrentUniverseId_Uint64) return 1;
        if(prop == vr::Prop_SupportedButtons_Uint64) return 0xFFFFFFFFFFFFFFFFULL;
        return 0;
    }
    virtual void GetMatrix34TrackedDeviceProperty(HmdMatrix34_t *pRet, vr::TrackedDeviceIndex_t unDeviceIndex, ETrackedDeviceProperty prop, ETrackedPropertyError *pError = 0L) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetMatrix34TrackedDeviceProperty\n"); fclose(_f); }
        if(pRet) { memset(pRet, 0, sizeof(*pRet)); }
        if(pRet) { memset(pRet, 0, sizeof(*pRet)); pRet->m[0][0] = 1; pRet->m[1][1] = 1; pRet->m[2][2] = 1; }
        if(pError) *pError = vr::TrackedProp_Success;
    }
    virtual uint32_t GetArrayTrackedDeviceProperty(vr::TrackedDeviceIndex_t unDeviceIndex, ETrackedDeviceProperty prop, PropertyTypeTag_t propType, void *pBuffer, uint32_t unBufferSize, ETrackedPropertyError *pError = 0L) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetArrayTrackedDeviceProperty\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual uint32_t GetStringTrackedDeviceProperty(vr::TrackedDeviceIndex_t unDeviceIndex, ETrackedDeviceProperty prop, VR_OUT_STRING() char *pchValue, uint32_t unBufferSize, ETrackedPropertyError *pError = 0L) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetStringTrackedDeviceProperty\n"); fclose(_f); }
        const char* s = "Generic";
        if (prop == vr::Prop_RenderModelName_String) {
            if (unDeviceIndex == 0) s = "generic_hmd";
            else if (unDeviceIndex == 1) s = "{indexcontroller}valve_controller_knu_1_0_left";
            else if (unDeviceIndex == 2) s = "{indexcontroller}valve_controller_knu_1_0_right";
        }
        if (prop == vr::Prop_ControllerType_String) s = "knuckles";
        if (prop == vr::Prop_TrackingSystemName_String) s = "lighthouse";
        if (prop == vr::Prop_ManufacturerName_String) s = "Valve";
        if(pchValue && unBufferSize > 0) { strncpy(pchValue, s, unBufferSize - 1); pchValue[unBufferSize - 1] = '\0'; }
        if(pError) *pError = vr::TrackedProp_Success;
        return (uint32_t)strlen(s) + 1;
    }
    virtual const char * GetPropErrorNameFromEnum(ETrackedPropertyError error) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetPropErrorNameFromEnum\n"); fclose(_f); }
        return "1.10.30";
    }
    virtual bool PollNextEvent(VREvent_t *pEvent, uint32_t uncbVREvent) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::PollNextEvent\n"); fclose(_f); }
        static int count = 0; if (count == 0) { count++; if(pEvent) { memset(pEvent, 0, uncbVREvent); pEvent->eventType = (vr::EVREventType)100; pEvent->trackedDeviceIndex = 0; } return true; } else if (count == 1) { count++; if(pEvent) { memset(pEvent, 0, uncbVREvent); pEvent->eventType = (vr::EVREventType)403; pEvent->trackedDeviceIndex = 0; } return true; } return false;
    }
    virtual bool PollNextEventWithPose(ETrackingUniverseOrigin eOrigin, VREvent_t *pEvent, uint32_t uncbVREvent, vr::TrackedDevicePose_t *pTrackedDevicePose) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::PollNextEventWithPose\n"); fclose(_f); }
        return false;
    }
    virtual const char * GetEventTypeNameFromEnum(EVREventType eType) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetEventTypeNameFromEnum\n"); fclose(_f); }
        return "1.10.30";
    }
    virtual void GetHiddenAreaMesh(HiddenAreaMesh_t *pRet, EVREye eEye, EHiddenAreaMeshType type = k_eHiddenAreaMesh_Standard) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetHiddenAreaMesh\n"); fclose(_f); }
        if(pRet) { memset(pRet, 0, sizeof(*pRet)); }
        if(pRet) { pRet->pVertexData = nullptr; pRet->unTriangleCount = 0; }
    }
    virtual bool GetControllerState(vr::TrackedDeviceIndex_t unControllerDeviceIndex, vr::VRControllerState_t *pControllerState, uint32_t unControllerStateSize) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetControllerState\n"); fclose(_f); }
        if(pControllerState) memset(pControllerState, 0, unControllerStateSize);
        return true;
    }
    virtual bool GetControllerStateWithPose(ETrackingUniverseOrigin eOrigin, vr::TrackedDeviceIndex_t unControllerDeviceIndex, vr::VRControllerState_t *pControllerState, uint32_t unControllerStateSize, TrackedDevicePose_t *pTrackedDevicePose) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetControllerStateWithPose\n"); fclose(_f); }
        if(pControllerState) memset(pControllerState, 0, unControllerStateSize);
        return true;
    }
    virtual void TriggerHapticPulse(vr::TrackedDeviceIndex_t unControllerDeviceIndex, uint32_t unAxisId, unsigned short usDurationMicroSec) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::TriggerHapticPulse\n"); fclose(_f); }
    }
    virtual const char * GetButtonIdNameFromEnum(EVRButtonId eButtonId) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetButtonIdNameFromEnum\n"); fclose(_f); }
        return "1.10.30";
    }
    virtual const char * GetControllerAxisTypeNameFromEnum(EVRControllerAxisType eAxisType) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetControllerAxisTypeNameFromEnum\n"); fclose(_f); }
        return "1.10.30";
    }
    virtual bool IsInputAvailable() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::IsInputAvailable\n"); fclose(_f); }
        return true;
    }
    virtual bool IsSteamVRDrawingControllers() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::IsSteamVRDrawingControllers\n"); fclose(_f); }
        return false;
    }
    virtual bool ShouldApplicationPause() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::ShouldApplicationPause\n"); fclose(_f); }
        return false;
    }
    virtual bool ShouldApplicationReduceRenderingWork() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::ShouldApplicationReduceRenderingWork\n"); fclose(_f); }
        return false;
    }
    virtual vr::EVRFirmwareError PerformFirmwareUpdate(vr::TrackedDeviceIndex_t unDeviceIndex) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::PerformFirmwareUpdate\n"); fclose(_f); }
        return (vr::EVRFirmwareError)1;
    }
    virtual void AcknowledgeQuit_Exiting() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::AcknowledgeQuit_Exiting\n"); fclose(_f); }
    }
    virtual uint32_t GetAppContainerFilePaths(VR_OUT_STRING() char *pchBuffer, uint32_t unBufferSize) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetAppContainerFilePaths\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual const char * GetRuntimeVersion() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSystem::GetRuntimeVersion\n"); fclose(_f); }
        return "1.10.30";
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockSystem;

class Mock_IVRApplications : public vr::IVRApplications {
public:
    virtual EVRApplicationError AddApplicationManifest(const char *pchApplicationManifestFullPath, bool bTemporary = false) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::AddApplicationManifest\n"); fclose(_f); }
        return (EVRApplicationError)1;
    }
    virtual EVRApplicationError RemoveApplicationManifest(const char *pchApplicationManifestFullPath) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::RemoveApplicationManifest\n"); fclose(_f); }
        return (EVRApplicationError)1;
    }
    virtual bool IsApplicationInstalled(const char *pchAppKey) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::IsApplicationInstalled\n"); fclose(_f); }
        return false;
    }
    virtual uint32_t GetApplicationCount() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::GetApplicationCount\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual EVRApplicationError GetApplicationKeyByIndex(uint32_t unApplicationIndex, VR_OUT_STRING() char *pchAppKeyBuffer, uint32_t unAppKeyBufferLen) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::GetApplicationKeyByIndex\n"); fclose(_f); }
        return (EVRApplicationError)1;
    }
    virtual EVRApplicationError GetApplicationKeyByProcessId(uint32_t unProcessId, VR_OUT_STRING() char *pchAppKeyBuffer, uint32_t unAppKeyBufferLen) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::GetApplicationKeyByProcessId\n"); fclose(_f); }
        return (EVRApplicationError)1;
    }
    virtual EVRApplicationError LaunchApplication(const char *pchAppKey) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::LaunchApplication\n"); fclose(_f); }
        return (EVRApplicationError)1;
    }
    virtual EVRApplicationError LaunchTemplateApplication(const char *pchTemplateAppKey, const char *pchNewAppKey, VR_ARRAY_COUNT( unKeys ) const AppOverrideKeys_t *pKeys, uint32_t unKeys) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::LaunchTemplateApplication\n"); fclose(_f); }
        return (EVRApplicationError)1;
    }
    virtual vr::EVRApplicationError LaunchApplicationFromMimeType(const char *pchMimeType, const char *pchArgs) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::LaunchApplicationFromMimeType\n"); fclose(_f); }
        return (vr::EVRApplicationError)1;
    }
    virtual EVRApplicationError LaunchDashboardOverlay(const char *pchAppKey) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::LaunchDashboardOverlay\n"); fclose(_f); }
        return (EVRApplicationError)1;
    }
    virtual bool CancelApplicationLaunch(const char *pchAppKey) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::CancelApplicationLaunch\n"); fclose(_f); }
        return false;
    }
    virtual EVRApplicationError IdentifyApplication(uint32_t unProcessId, const char *pchAppKey) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::IdentifyApplication\n"); fclose(_f); }
        return (EVRApplicationError)1;
    }
    virtual uint32_t GetApplicationProcessId(const char *pchAppKey) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::GetApplicationProcessId\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual const char * GetApplicationsErrorNameFromEnum(EVRApplicationError error) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::GetApplicationsErrorNameFromEnum\n"); fclose(_f); }
        return "1.10.30";
    }
    virtual uint32_t GetApplicationPropertyString(const char *pchAppKey, EVRApplicationProperty eProperty, VR_OUT_STRING() char *pchPropertyValueBuffer, uint32_t unPropertyValueBufferLen, EVRApplicationError *peError = nullptr) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::GetApplicationPropertyString\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual bool GetApplicationPropertyBool(const char *pchAppKey, EVRApplicationProperty eProperty, EVRApplicationError *peError = nullptr) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::GetApplicationPropertyBool\n"); fclose(_f); }
        return false;
    }
    virtual uint64_t GetApplicationPropertyUint64(const char *pchAppKey, EVRApplicationProperty eProperty, EVRApplicationError *peError = nullptr) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::GetApplicationPropertyUint64\n"); fclose(_f); }
        return (uint64_t)0;
    }
    virtual EVRApplicationError SetApplicationAutoLaunch(const char *pchAppKey, bool bAutoLaunch) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::SetApplicationAutoLaunch\n"); fclose(_f); }
        return (EVRApplicationError)1;
    }
    virtual bool GetApplicationAutoLaunch(const char *pchAppKey) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::GetApplicationAutoLaunch\n"); fclose(_f); }
        return false;
    }
    virtual EVRApplicationError SetDefaultApplicationForMimeType(const char *pchAppKey, const char *pchMimeType) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::SetDefaultApplicationForMimeType\n"); fclose(_f); }
        return (EVRApplicationError)1;
    }
    virtual bool GetDefaultApplicationForMimeType(const char *pchMimeType, VR_OUT_STRING() char *pchAppKeyBuffer, uint32_t unAppKeyBufferLen) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::GetDefaultApplicationForMimeType\n"); fclose(_f); }
        return false;
    }
    virtual bool GetApplicationSupportedMimeTypes(const char *pchAppKey, VR_OUT_STRING() char *pchMimeTypesBuffer, uint32_t unMimeTypesBuffer) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::GetApplicationSupportedMimeTypes\n"); fclose(_f); }
        return false;
    }
    virtual uint32_t GetApplicationsThatSupportMimeType(const char *pchMimeType, VR_OUT_STRING() char *pchAppKeysThatSupportBuffer, uint32_t unAppKeysThatSupportBuffer) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::GetApplicationsThatSupportMimeType\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual uint32_t GetApplicationLaunchArguments(uint32_t unHandle, VR_OUT_STRING() char *pchArgs, uint32_t unArgs) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::GetApplicationLaunchArguments\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual EVRApplicationError GetStartingApplication(VR_OUT_STRING() char *pchAppKeyBuffer, uint32_t unAppKeyBufferLen) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::GetStartingApplication\n"); fclose(_f); }
        return (EVRApplicationError)1;
    }
    virtual EVRSceneApplicationState GetSceneApplicationState() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::GetSceneApplicationState\n"); fclose(_f); }
        return (EVRSceneApplicationState)0;
    }
    virtual EVRApplicationError PerformApplicationPrelaunchCheck(const char *pchAppKey) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::PerformApplicationPrelaunchCheck\n"); fclose(_f); }
        return (EVRApplicationError)1;
    }
    virtual const char * GetSceneApplicationStateNameFromEnum(EVRSceneApplicationState state) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::GetSceneApplicationStateNameFromEnum\n"); fclose(_f); }
        return "1.10.30";
    }
    virtual EVRApplicationError LaunchInternalProcess(const char *pchBinaryPath, const char *pchArguments, const char *pchWorkingDirectory) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::LaunchInternalProcess\n"); fclose(_f); }
        return (EVRApplicationError)1;
    }
    virtual uint32_t GetCurrentSceneProcessId() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRApplications::GetCurrentSceneProcessId\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockApplications;

class Mock_IVRSettings : public vr::IVRSettings {
public:
    virtual const char * GetSettingsErrorNameFromEnum(EVRSettingsError eError) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSettings::GetSettingsErrorNameFromEnum\n"); fclose(_f); }
        return "1.10.30";
    }
    virtual void SetBool(const char *pchSection, const char *pchSettingsKey, bool bValue, EVRSettingsError *peError = nullptr) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSettings::SetBool\n"); fclose(_f); }
    }
    virtual void SetInt32(const char *pchSection, const char *pchSettingsKey, int32_t nValue, EVRSettingsError *peError = nullptr) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSettings::SetInt32\n"); fclose(_f); }
    }
    virtual void SetFloat(const char *pchSection, const char *pchSettingsKey, float flValue, EVRSettingsError *peError = nullptr) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSettings::SetFloat\n"); fclose(_f); }
    }
    virtual void SetString(const char *pchSection, const char *pchSettingsKey, const char *pchValue, EVRSettingsError *peError = nullptr) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSettings::SetString\n"); fclose(_f); }
    }
    virtual bool GetBool(const char *pchSection, const char *pchSettingsKey, EVRSettingsError *peError = nullptr) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSettings::GetBool\n"); fclose(_f); }
        return false;
    }
    virtual int32_t GetInt32(const char *pchSection, const char *pchSettingsKey, EVRSettingsError *peError = nullptr) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSettings::GetInt32\n"); fclose(_f); }
        return (int32_t)0;
    }
    virtual float GetFloat(const char *pchSection, const char *pchSettingsKey, EVRSettingsError *peError = nullptr) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSettings::GetFloat\n"); fclose(_f); }
        return (float)0;
    }
    virtual void GetString(const char *pchSection, const char *pchSettingsKey, VR_OUT_STRING() char *pchValue, uint32_t unValueLen, EVRSettingsError *peError = nullptr) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSettings::GetString\n"); fclose(_f); }
        if(peError) *peError = vr::VRSettingsError_None;
        if(pchValue && unValueLen > 0) pchValue[0] = '\0';
    }
    virtual void RemoveSection(const char *pchSection, EVRSettingsError *peError = nullptr) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSettings::RemoveSection\n"); fclose(_f); }
    }
    virtual void RemoveKeyInSection(const char *pchSection, const char *pchSettingsKey, EVRSettingsError *peError = nullptr) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSettings::RemoveKeyInSection\n"); fclose(_f); }
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockSettings;

class Mock_IVRChaperone : public vr::IVRChaperone {
public:
    virtual ChaperoneCalibrationState GetCalibrationState() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperone::GetCalibrationState\n"); fclose(_f); }
        return (ChaperoneCalibrationState)0;
    }
    virtual bool GetPlayAreaSize(float *pSizeX, float *pSizeZ) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperone::GetPlayAreaSize\n"); fclose(_f); }
        return false;
    }
    virtual bool GetPlayAreaRect(HmdQuad_t *rect) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperone::GetPlayAreaRect\n"); fclose(_f); }
        return false;
    }
    virtual void ReloadInfo(void) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperone::ReloadInfo\n"); fclose(_f); }
    }
    virtual void SetSceneColor(HmdColor_t color) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperone::SetSceneColor\n"); fclose(_f); }
    }
    virtual void GetBoundsColor(HmdColor_t *pOutputColorArray, int nNumOutputColors, float flCollisionBoundsFadeDistance, HmdColor_t *pOutputCameraColor) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperone::GetBoundsColor\n"); fclose(_f); }
    }
    virtual bool AreBoundsVisible() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperone::AreBoundsVisible\n"); fclose(_f); }
        return false;
    }
    virtual void ForceBoundsVisible(bool bForce) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperone::ForceBoundsVisible\n"); fclose(_f); }
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockChaperone;

class Mock_IVRChaperoneSetup : public vr::IVRChaperoneSetup {
public:
    virtual bool CommitWorkingCopy(EChaperoneConfigFile configFile) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::CommitWorkingCopy\n"); fclose(_f); }
        return false;
    }
    virtual void RevertWorkingCopy() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::RevertWorkingCopy\n"); fclose(_f); }
    }
    virtual bool GetWorkingPlayAreaSize(float *pSizeX, float *pSizeZ) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::GetWorkingPlayAreaSize\n"); fclose(_f); }
        return false;
    }
    virtual bool GetWorkingPlayAreaRect(HmdQuad_t *rect) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::GetWorkingPlayAreaRect\n"); fclose(_f); }
        return false;
    }
    virtual bool GetWorkingCollisionBoundsInfo(VR_OUT_ARRAY_COUNT(punQuadsCount) HmdQuad_t *pQuadsBuffer, uint32_t* punQuadsCount) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::GetWorkingCollisionBoundsInfo\n"); fclose(_f); }
        return false;
    }
    virtual bool GetLiveCollisionBoundsInfo(VR_OUT_ARRAY_COUNT(punQuadsCount) HmdQuad_t *pQuadsBuffer, uint32_t* punQuadsCount) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::GetLiveCollisionBoundsInfo\n"); fclose(_f); }
        return false;
    }
    virtual bool GetWorkingSeatedZeroPoseToRawTrackingPose(HmdMatrix34_t *pmatSeatedZeroPoseToRawTrackingPose) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::GetWorkingSeatedZeroPoseToRawTrackingPose\n"); fclose(_f); }
        return false;
    }
    virtual bool GetWorkingStandingZeroPoseToRawTrackingPose(HmdMatrix34_t *pmatStandingZeroPoseToRawTrackingPose) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::GetWorkingStandingZeroPoseToRawTrackingPose\n"); fclose(_f); }
        return false;
    }
    virtual void SetWorkingPlayAreaSize(float sizeX, float sizeZ) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::SetWorkingPlayAreaSize\n"); fclose(_f); }
    }
    virtual void SetWorkingCollisionBoundsInfo(VR_ARRAY_COUNT(unQuadsCount) HmdQuad_t *pQuadsBuffer, uint32_t unQuadsCount) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::SetWorkingCollisionBoundsInfo\n"); fclose(_f); }
    }
    virtual void SetWorkingPerimeter(VR_ARRAY_COUNT( unPointCount ) HmdVector2_t *pPointBuffer, uint32_t unPointCount) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::SetWorkingPerimeter\n"); fclose(_f); }
    }
    virtual void SetWorkingSeatedZeroPoseToRawTrackingPose(const HmdMatrix34_t *pMatSeatedZeroPoseToRawTrackingPose) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::SetWorkingSeatedZeroPoseToRawTrackingPose\n"); fclose(_f); }
    }
    virtual void SetWorkingStandingZeroPoseToRawTrackingPose(const HmdMatrix34_t *pMatStandingZeroPoseToRawTrackingPose) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::SetWorkingStandingZeroPoseToRawTrackingPose\n"); fclose(_f); }
    }
    virtual void ReloadFromDisk(EChaperoneConfigFile configFile) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::ReloadFromDisk\n"); fclose(_f); }
    }
    virtual bool GetLiveSeatedZeroPoseToRawTrackingPose(HmdMatrix34_t *pmatSeatedZeroPoseToRawTrackingPose) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::GetLiveSeatedZeroPoseToRawTrackingPose\n"); fclose(_f); }
        return false;
    }
    virtual bool ExportLiveToBuffer(VR_OUT_STRING() char *pBuffer, uint32_t *pnBufferLength) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::ExportLiveToBuffer\n"); fclose(_f); }
        return false;
    }
    virtual bool ImportFromBufferToWorking(const char *pBuffer, uint32_t nImportFlags) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::ImportFromBufferToWorking\n"); fclose(_f); }
        return false;
    }
    virtual void ShowWorkingSetPreview() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::ShowWorkingSetPreview\n"); fclose(_f); }
    }
    virtual void HideWorkingSetPreview() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::HideWorkingSetPreview\n"); fclose(_f); }
    }
    virtual void RoomSetupStarting() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRChaperoneSetup::RoomSetupStarting\n"); fclose(_f); }
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockChaperoneSetup;

class Mock_IVRCompositor : public vr::IVRCompositor {
public:
    virtual void SetTrackingSpace(ETrackingUniverseOrigin eOrigin) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::SetTrackingSpace\n"); fclose(_f); }
    }
    virtual ETrackingUniverseOrigin GetTrackingSpace() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::GetTrackingSpace\n"); fclose(_f); }
        return (ETrackingUniverseOrigin)0;
    }
    virtual EVRCompositorError WaitGetPoses(VR_ARRAY_COUNT( unRenderPoseArrayCount ) TrackedDevicePose_t* pRenderPoseArray, uint32_t unRenderPoseArrayCount, VR_ARRAY_COUNT( unGamePoseArrayCount ) TrackedDevicePose_t* pGamePoseArray, uint32_t unGamePoseArrayCount) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::WaitGetPoses\n"); fclose(_f); }
        if(pRenderPoseArray && unRenderPoseArrayCount > 0) {
            memset(pRenderPoseArray, 0, sizeof(vr::TrackedDevicePose_t) * unRenderPoseArrayCount);
            for(uint32_t i=0; i<3 && i<unRenderPoseArrayCount; ++i) {
                pRenderPoseArray[i].bPoseIsValid = true;
                pRenderPoseArray[i].bDeviceIsConnected = true;
                pRenderPoseArray[i].eTrackingResult = vr::TrackingResult_Running_OK;
                if (i == 1 && pSharedHands && pSharedHands->leftTransform[0] != 0.0f) {
                    for(int r=0;r<3;r++) for(int c=0;c<4;c++) pRenderPoseArray[i].mDeviceToAbsoluteTracking.m[r][c] = pSharedHands->leftTransform[c*4 + r];
                } else if (i == 2 && pSharedHands && pSharedHands->rightTransform[0] != 0.0f) {
                    for(int r=0;r<3;r++) for(int c=0;c<4;c++) pRenderPoseArray[i].mDeviceToAbsoluteTracking.m[r][c] = pSharedHands->rightTransform[c*4 + r];
                } else {
                    pRenderPoseArray[i].mDeviceToAbsoluteTracking.m[0][0] = 1; pRenderPoseArray[i].mDeviceToAbsoluteTracking.m[1][1] = 1; pRenderPoseArray[i].mDeviceToAbsoluteTracking.m[2][2] = 1;
                }
            }
        }
        if(pGamePoseArray && unGamePoseArrayCount > 0) {
            memset(pGamePoseArray, 0, sizeof(vr::TrackedDevicePose_t) * unGamePoseArrayCount);
            for(uint32_t i=0; i<3 && i<unGamePoseArrayCount; ++i) {
                pGamePoseArray[i].bPoseIsValid = true;
                pGamePoseArray[i].bDeviceIsConnected = true;
                pGamePoseArray[i].eTrackingResult = vr::TrackingResult_Running_OK;
                if (i == 1 && pSharedHands && pSharedHands->leftTransform[0] != 0.0f) {
                    for(int r=0;r<3;r++) for(int c=0;c<4;c++) pGamePoseArray[i].mDeviceToAbsoluteTracking.m[r][c] = pSharedHands->leftTransform[c*4 + r];
                } else if (i == 2 && pSharedHands && pSharedHands->rightTransform[0] != 0.0f) {
                    for(int r=0;r<3;r++) for(int c=0;c<4;c++) pGamePoseArray[i].mDeviceToAbsoluteTracking.m[r][c] = pSharedHands->rightTransform[c*4 + r];
                } else {
                    pGamePoseArray[i].mDeviceToAbsoluteTracking.m[0][0] = 1; pGamePoseArray[i].mDeviceToAbsoluteTracking.m[1][1] = 1; pGamePoseArray[i].mDeviceToAbsoluteTracking.m[2][2] = 1;
                }
            }
        }
        Sleep(11);
        return vr::VRCompositorError_None;
    }
    virtual EVRCompositorError GetLastPoses(VR_ARRAY_COUNT( unRenderPoseArrayCount ) TrackedDevicePose_t* pRenderPoseArray, uint32_t unRenderPoseArrayCount, VR_ARRAY_COUNT( unGamePoseArrayCount ) TrackedDevicePose_t* pGamePoseArray, uint32_t unGamePoseArrayCount) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::GetLastPoses\n"); fclose(_f); }
        return (EVRCompositorError)1;
    }
    virtual EVRCompositorError GetLastPoseForTrackedDeviceIndex(TrackedDeviceIndex_t unDeviceIndex, TrackedDevicePose_t *pOutputPose, TrackedDevicePose_t *pOutputGamePose) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::GetLastPoseForTrackedDeviceIndex\n"); fclose(_f); }
        return (EVRCompositorError)1;
    }
    virtual EVRCompositorError Submit(EVREye eEye, const Texture_t *pTexture, const VRTextureBounds_t* pBounds = 0, EVRSubmitFlags nSubmitFlags = Submit_Default) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::Submit\n"); fclose(_f); }
        if (eEye != vr::Eye_Left) return vr::VRCompositorError_None;
        if(pTexture && pTexture->handle && pTexture->eType == vr::TextureType_DirectX) {
            ID3D11Texture2D* pGameTex = (ID3D11Texture2D*)pTexture->handle;
            D3D11_TEXTURE2D_DESC desc;
            pGameTex->GetDesc(&desc);
            
            ID3D11Device* pDevice = nullptr;
            pGameTex->GetDevice(&pDevice);
            
            if (pDevice) {
                ID3D11DeviceContext* pContext = nullptr;
                pDevice->GetImmediateContext(&pContext);
                
                if (pContext) {
                    if (!pStagingTexture) {
                        D3D11_TEXTURE2D_DESC stDesc = desc;
                        stDesc.Usage = D3D11_USAGE_STAGING;
                        stDesc.BindFlags = 0;
                        stDesc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
                        stDesc.MiscFlags = 0;
                        pDevice->CreateTexture2D(&stDesc, nullptr, &pStagingTexture);
                    }
                    
                    if (pStagingTexture) {
                        pContext->CopyResource(pStagingTexture, pGameTex);
                        
                        D3D11_MAPPED_SUBRESOURCE mapped;
                        if (SUCCEEDED(pContext->Map(pStagingTexture, 0, D3D11_MAP_READ, 0, &mapped))) {
                            if (pHeader && pPixelData) {
                                pHeader->width = desc.Width;
                                pHeader->height = desc.Height;
                                pHeader->format = desc.Format;
                                
                                uint8_t* dst = pPixelData;
                                uint8_t* src = (uint8_t*)mapped.pData;
                                uint32_t bytesPerRow = desc.Width * 4;
                                
                                for(uint32_t y = 0; y < desc.Height; ++y) {
                                    memcpy(dst + y * bytesPerRow, src + y * mapped.RowPitch, bytesPerRow);
                                }
                                
                                pHeader->sequenceNumber = ++frameSeq;
                            }
                            pContext->Unmap(pStagingTexture, 0);
                        }
                    }
                    pContext->Release();
                }
                pDevice->Release();
            }
        }
        return vr::VRCompositorError_None;
    }
    virtual void ClearLastSubmittedFrame() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::ClearLastSubmittedFrame\n"); fclose(_f); }
    }
    virtual void PostPresentHandoff() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::PostPresentHandoff\n"); fclose(_f); }
    }
    virtual bool GetFrameTiming(Compositor_FrameTiming *pTiming, uint32_t unFramesAgo = 0) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::GetFrameTiming\n"); fclose(_f); }
        return false;
    }
    virtual uint32_t GetFrameTimings(VR_ARRAY_COUNT( nFrames ) Compositor_FrameTiming *pTiming, uint32_t nFrames) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::GetFrameTimings\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual float GetFrameTimeRemaining() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::GetFrameTimeRemaining\n"); fclose(_f); }
        return (float)0;
    }
    virtual void GetCumulativeStats(Compositor_CumulativeStats *pStats, uint32_t nStatsSizeInBytes) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::GetCumulativeStats\n"); fclose(_f); }
    }
    virtual void FadeToColor(float fSeconds, float fRed, float fGreen, float fBlue, float fAlpha, bool bBackground = false) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::FadeToColor\n"); fclose(_f); }
    }
    virtual void GetCurrentFadeColor(HmdColor_t *pRet, bool bBackground = false) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::GetCurrentFadeColor\n"); fclose(_f); }
        if(pRet) { memset(pRet, 0, sizeof(*pRet)); }
        if(pRet) { memset(pRet, 0, sizeof(*pRet)); }
    }
    virtual void FadeGrid(float fSeconds, bool bFadeIn) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::FadeGrid\n"); fclose(_f); }
    }
    virtual float GetCurrentGridAlpha() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::GetCurrentGridAlpha\n"); fclose(_f); }
        return (float)0;
    }
    virtual EVRCompositorError SetSkyboxOverride(VR_ARRAY_COUNT( unTextureCount ) const Texture_t *pTextures, uint32_t unTextureCount) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::SetSkyboxOverride\n"); fclose(_f); }
        return (EVRCompositorError)1;
    }
    virtual void ClearSkyboxOverride() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::ClearSkyboxOverride\n"); fclose(_f); }
    }
    virtual void CompositorBringToFront() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::CompositorBringToFront\n"); fclose(_f); }
    }
    virtual void CompositorGoToBack() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::CompositorGoToBack\n"); fclose(_f); }
    }
    virtual void CompositorQuit() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::CompositorQuit\n"); fclose(_f); }
    }
    virtual bool IsFullscreen() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::IsFullscreen\n"); fclose(_f); }
        return false;
    }
    virtual uint32_t GetCurrentSceneFocusProcess() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::GetCurrentSceneFocusProcess\n"); fclose(_f); }
        return GetCurrentProcessId();
    }
    virtual uint32_t GetLastFrameRenderer() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::GetLastFrameRenderer\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual bool CanRenderScene() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::CanRenderScene\n"); fclose(_f); }
        return true;
    }
    virtual void ShowMirrorWindow() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::ShowMirrorWindow\n"); fclose(_f); }
    }
    virtual void HideMirrorWindow() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::HideMirrorWindow\n"); fclose(_f); }
    }
    virtual bool IsMirrorWindowVisible() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::IsMirrorWindowVisible\n"); fclose(_f); }
        return false;
    }
    virtual void CompositorDumpImages() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::CompositorDumpImages\n"); fclose(_f); }
    }
    virtual bool ShouldAppRenderWithLowResources() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::ShouldAppRenderWithLowResources\n"); fclose(_f); }
        return false;
    }
    virtual void ForceInterleavedReprojectionOn(bool bOverride) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::ForceInterleavedReprojectionOn\n"); fclose(_f); }
    }
    virtual void ForceReconnectProcess() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::ForceReconnectProcess\n"); fclose(_f); }
    }
    virtual void SuspendRendering(bool bSuspend) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::SuspendRendering\n"); fclose(_f); }
    }
    virtual vr::EVRCompositorError GetMirrorTextureD3D11(vr::EVREye eEye, void *pD3D11DeviceOrResource, void **ppD3D11ShaderResourceView) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::GetMirrorTextureD3D11\n"); fclose(_f); }
        return (vr::EVRCompositorError)1;
    }
    virtual void ReleaseMirrorTextureD3D11(void *pD3D11ShaderResourceView) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::ReleaseMirrorTextureD3D11\n"); fclose(_f); }
    }
    virtual vr::EVRCompositorError GetMirrorTextureGL(vr::EVREye eEye, vr::glUInt_t *pglTextureId, vr::glSharedTextureHandle_t *pglSharedTextureHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::GetMirrorTextureGL\n"); fclose(_f); }
        return (vr::EVRCompositorError)1;
    }
    virtual bool ReleaseSharedGLTexture(vr::glUInt_t glTextureId, vr::glSharedTextureHandle_t glSharedTextureHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::ReleaseSharedGLTexture\n"); fclose(_f); }
        return false;
    }
    virtual void LockGLSharedTextureForAccess(vr::glSharedTextureHandle_t glSharedTextureHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::LockGLSharedTextureForAccess\n"); fclose(_f); }
    }
    virtual void UnlockGLSharedTextureForAccess(vr::glSharedTextureHandle_t glSharedTextureHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::UnlockGLSharedTextureForAccess\n"); fclose(_f); }
    }
    virtual uint32_t GetVulkanInstanceExtensionsRequired(VR_OUT_STRING() char *pchValue, uint32_t unBufferSize) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::GetVulkanInstanceExtensionsRequired\n"); fclose(_f); }
        if(pchValue && unBufferSize > 0) pchValue[0] = '\0';
        return 0;
    }
    virtual uint32_t GetVulkanDeviceExtensionsRequired(VkPhysicalDevice_T *pPhysicalDevice, VR_OUT_STRING() char *pchValue, uint32_t unBufferSize) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::GetVulkanDeviceExtensionsRequired\n"); fclose(_f); }
        if(pchValue && unBufferSize > 0) pchValue[0] = '\0';
        return 0;
    }
    virtual void SetExplicitTimingMode(EVRCompositorTimingMode eTimingMode) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::SetExplicitTimingMode\n"); fclose(_f); }
    }
    virtual EVRCompositorError SubmitExplicitTimingData() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::SubmitExplicitTimingData\n"); fclose(_f); }
        return (EVRCompositorError)1;
    }
    virtual bool IsMotionSmoothingEnabled() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::IsMotionSmoothingEnabled\n"); fclose(_f); }
        return false;
    }
    virtual bool IsMotionSmoothingSupported() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::IsMotionSmoothingSupported\n"); fclose(_f); }
        return false;
    }
    virtual bool IsCurrentSceneFocusAppLoading() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::IsCurrentSceneFocusAppLoading\n"); fclose(_f); }
        return false;
    }
    virtual EVRCompositorError SetStageOverride_Async(const char *pchRenderModelPath, const HmdMatrix34_t *pTransform = 0, const Compositor_StageRenderSettings *pRenderSettings = 0, uint32_t nSizeOfRenderSettings = 0) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::SetStageOverride_Async\n"); fclose(_f); }
        return (EVRCompositorError)1;
    }
    virtual void ClearStageOverride() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::ClearStageOverride\n"); fclose(_f); }
    }
    virtual bool GetCompositorBenchmarkResults(Compositor_BenchmarkResults *pBenchmarkResults, uint32_t nSizeOfBenchmarkResults) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::GetCompositorBenchmarkResults\n"); fclose(_f); }
        return false;
    }
    virtual EVRCompositorError GetLastPosePredictionIDs(uint32_t *pRenderPosePredictionID, uint32_t *pGamePosePredictionID) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::GetLastPosePredictionIDs\n"); fclose(_f); }
        return (EVRCompositorError)1;
    }
    virtual EVRCompositorError GetPosesForFrame(uint32_t unPosePredictionID, VR_ARRAY_COUNT( unPoseArrayCount ) TrackedDevicePose_t* pPoseArray, uint32_t unPoseArrayCount) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRCompositor::GetPosesForFrame\n"); fclose(_f); }
        return (EVRCompositorError)1;
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockCompositor;

class Mock_IVRHeadsetView : public vr::IVRHeadsetView {
public:
    virtual void SetHeadsetViewSize(uint32_t nWidth, uint32_t nHeight) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRHeadsetView::SetHeadsetViewSize\n"); fclose(_f); }
    }
    virtual void GetHeadsetViewSize(uint32_t *pnWidth, uint32_t *pnHeight) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRHeadsetView::GetHeadsetViewSize\n"); fclose(_f); }
    }
    virtual void SetHeadsetViewMode(HeadsetViewMode_t eHeadsetViewMode) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRHeadsetView::SetHeadsetViewMode\n"); fclose(_f); }
    }
    virtual HeadsetViewMode_t GetHeadsetViewMode() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRHeadsetView::GetHeadsetViewMode\n"); fclose(_f); }
        return (HeadsetViewMode_t)0;
    }
    virtual void SetHeadsetViewCropped(bool bCropped) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRHeadsetView::SetHeadsetViewCropped\n"); fclose(_f); }
    }
    virtual bool GetHeadsetViewCropped() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRHeadsetView::GetHeadsetViewCropped\n"); fclose(_f); }
        return false;
    }
    virtual float GetHeadsetViewAspectRatio() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRHeadsetView::GetHeadsetViewAspectRatio\n"); fclose(_f); }
        return (float)0;
    }
    virtual void SetHeadsetViewBlendRange(float flStartPct, float flEndPct) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRHeadsetView::SetHeadsetViewBlendRange\n"); fclose(_f); }
    }
    virtual void GetHeadsetViewBlendRange(float *pStartPct, float *pEndPct) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRHeadsetView::GetHeadsetViewBlendRange\n"); fclose(_f); }
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockHeadsetView;

class Mock_IVRNotifications : public vr::IVRNotifications {
public:
    virtual EVRNotificationError CreateNotification(VROverlayHandle_t ulOverlayHandle, uint64_t ulUserValue, EVRNotificationType type, const char *pchText, EVRNotificationStyle style, const NotificationBitmap_t *pImage, VRNotificationId *pNotificationId) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRNotifications::CreateNotification\n"); fclose(_f); }
        return (EVRNotificationError)1;
    }
    virtual EVRNotificationError RemoveNotification(VRNotificationId notificationId) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRNotifications::RemoveNotification\n"); fclose(_f); }
        return (EVRNotificationError)1;
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockNotifications;

class Mock_IVROverlay : public vr::IVROverlay {
public:
    virtual EVROverlayError FindOverlay(const char *pchOverlayKey, VROverlayHandle_t * pOverlayHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::FindOverlay\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError CreateOverlay(const char *pchOverlayKey, const char *pchOverlayName, VROverlayHandle_t * pOverlayHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::CreateOverlay\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError DestroyOverlay(VROverlayHandle_t ulOverlayHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::DestroyOverlay\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual uint32_t GetOverlayKey(VROverlayHandle_t ulOverlayHandle, VR_OUT_STRING() char *pchValue, uint32_t unBufferSize, EVROverlayError *pError = 0L) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayKey\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual uint32_t GetOverlayName(VROverlayHandle_t ulOverlayHandle, VR_OUT_STRING() char *pchValue, uint32_t unBufferSize, EVROverlayError *pError = 0L) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayName\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual EVROverlayError SetOverlayName(VROverlayHandle_t ulOverlayHandle, const char *pchName) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayName\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetOverlayImageData(VROverlayHandle_t ulOverlayHandle, void *pvBuffer, uint32_t unBufferSize, uint32_t *punWidth, uint32_t *punHeight) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayImageData\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual const char * GetOverlayErrorNameFromEnum(EVROverlayError error) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayErrorNameFromEnum\n"); fclose(_f); }
        return "1.10.30";
    }
    virtual EVROverlayError SetOverlayRenderingPid(VROverlayHandle_t ulOverlayHandle, uint32_t unPID) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayRenderingPid\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual uint32_t GetOverlayRenderingPid(VROverlayHandle_t ulOverlayHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayRenderingPid\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual EVROverlayError SetOverlayFlag(VROverlayHandle_t ulOverlayHandle, VROverlayFlags eOverlayFlag, bool bEnabled) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayFlag\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetOverlayFlag(VROverlayHandle_t ulOverlayHandle, VROverlayFlags eOverlayFlag, bool *pbEnabled) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayFlag\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetOverlayFlags(VROverlayHandle_t ulOverlayHandle, uint32_t *pFlags) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayFlags\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlayColor(VROverlayHandle_t ulOverlayHandle, float fRed, float fGreen, float fBlue) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayColor\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetOverlayColor(VROverlayHandle_t ulOverlayHandle, float *pfRed, float *pfGreen, float *pfBlue) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayColor\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlayAlpha(VROverlayHandle_t ulOverlayHandle, float fAlpha) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayAlpha\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetOverlayAlpha(VROverlayHandle_t ulOverlayHandle, float *pfAlpha) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayAlpha\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlayTexelAspect(VROverlayHandle_t ulOverlayHandle, float fTexelAspect) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayTexelAspect\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetOverlayTexelAspect(VROverlayHandle_t ulOverlayHandle, float *pfTexelAspect) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayTexelAspect\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlaySortOrder(VROverlayHandle_t ulOverlayHandle, uint32_t unSortOrder) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlaySortOrder\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetOverlaySortOrder(VROverlayHandle_t ulOverlayHandle, uint32_t *punSortOrder) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlaySortOrder\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlayWidthInMeters(VROverlayHandle_t ulOverlayHandle, float fWidthInMeters) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayWidthInMeters\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetOverlayWidthInMeters(VROverlayHandle_t ulOverlayHandle, float *pfWidthInMeters) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayWidthInMeters\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlayCurvature(VROverlayHandle_t ulOverlayHandle, float fCurvature) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayCurvature\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetOverlayCurvature(VROverlayHandle_t ulOverlayHandle, float *pfCurvature) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayCurvature\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlayTextureColorSpace(VROverlayHandle_t ulOverlayHandle, EColorSpace eTextureColorSpace) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayTextureColorSpace\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetOverlayTextureColorSpace(VROverlayHandle_t ulOverlayHandle, EColorSpace *peTextureColorSpace) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayTextureColorSpace\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlayTextureBounds(VROverlayHandle_t ulOverlayHandle, const VRTextureBounds_t *pOverlayTextureBounds) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayTextureBounds\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetOverlayTextureBounds(VROverlayHandle_t ulOverlayHandle, VRTextureBounds_t *pOverlayTextureBounds) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayTextureBounds\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetOverlayTransformType(VROverlayHandle_t ulOverlayHandle, VROverlayTransformType *peTransformType) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayTransformType\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlayTransformAbsolute(VROverlayHandle_t ulOverlayHandle, ETrackingUniverseOrigin eTrackingOrigin, const HmdMatrix34_t *pmatTrackingOriginToOverlayTransform) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayTransformAbsolute\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetOverlayTransformAbsolute(VROverlayHandle_t ulOverlayHandle, ETrackingUniverseOrigin *peTrackingOrigin, HmdMatrix34_t *pmatTrackingOriginToOverlayTransform) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayTransformAbsolute\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlayTransformTrackedDeviceRelative(VROverlayHandle_t ulOverlayHandle, TrackedDeviceIndex_t unTrackedDevice, const HmdMatrix34_t *pmatTrackedDeviceToOverlayTransform) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayTransformTrackedDeviceRelative\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetOverlayTransformTrackedDeviceRelative(VROverlayHandle_t ulOverlayHandle, TrackedDeviceIndex_t *punTrackedDevice, HmdMatrix34_t *pmatTrackedDeviceToOverlayTransform) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayTransformTrackedDeviceRelative\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlayTransformTrackedDeviceComponent(VROverlayHandle_t ulOverlayHandle, TrackedDeviceIndex_t unDeviceIndex, const char *pchComponentName) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayTransformTrackedDeviceComponent\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetOverlayTransformTrackedDeviceComponent(VROverlayHandle_t ulOverlayHandle, TrackedDeviceIndex_t *punDeviceIndex, VR_OUT_STRING() char *pchComponentName, uint32_t unComponentNameSize) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayTransformTrackedDeviceComponent\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual vr::EVROverlayError GetOverlayTransformOverlayRelative(VROverlayHandle_t ulOverlayHandle, VROverlayHandle_t *ulOverlayHandleParent, HmdMatrix34_t *pmatParentOverlayToOverlayTransform) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayTransformOverlayRelative\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual vr::EVROverlayError SetOverlayTransformOverlayRelative(VROverlayHandle_t ulOverlayHandle, VROverlayHandle_t ulOverlayHandleParent, const HmdMatrix34_t *pmatParentOverlayToOverlayTransform) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayTransformOverlayRelative\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlayTransformCursor(VROverlayHandle_t ulCursorOverlayHandle, const HmdVector2_t *pvHotspot) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayTransformCursor\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual vr::EVROverlayError GetOverlayTransformCursor(VROverlayHandle_t ulOverlayHandle, HmdVector2_t *pvHotspot) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayTransformCursor\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError ShowOverlay(VROverlayHandle_t ulOverlayHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::ShowOverlay\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError HideOverlay(VROverlayHandle_t ulOverlayHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::HideOverlay\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual bool IsOverlayVisible(VROverlayHandle_t ulOverlayHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::IsOverlayVisible\n"); fclose(_f); }
        return false;
    }
    virtual EVROverlayError GetTransformForOverlayCoordinates(VROverlayHandle_t ulOverlayHandle, ETrackingUniverseOrigin eTrackingOrigin, HmdVector2_t coordinatesInOverlay, HmdMatrix34_t *pmatTransform) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetTransformForOverlayCoordinates\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual bool PollNextOverlayEvent(VROverlayHandle_t ulOverlayHandle, VREvent_t *pEvent, uint32_t uncbVREvent) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::PollNextOverlayEvent\n"); fclose(_f); }
        return false;
    }
    virtual EVROverlayError GetOverlayInputMethod(VROverlayHandle_t ulOverlayHandle, VROverlayInputMethod *peInputMethod) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayInputMethod\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlayInputMethod(VROverlayHandle_t ulOverlayHandle, VROverlayInputMethod eInputMethod) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayInputMethod\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetOverlayMouseScale(VROverlayHandle_t ulOverlayHandle, HmdVector2_t *pvecMouseScale) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayMouseScale\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlayMouseScale(VROverlayHandle_t ulOverlayHandle, const HmdVector2_t *pvecMouseScale) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayMouseScale\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual bool ComputeOverlayIntersection(VROverlayHandle_t ulOverlayHandle, const VROverlayIntersectionParams_t *pParams, VROverlayIntersectionResults_t *pResults) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::ComputeOverlayIntersection\n"); fclose(_f); }
        return false;
    }
    virtual bool IsHoverTargetOverlay(VROverlayHandle_t ulOverlayHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::IsHoverTargetOverlay\n"); fclose(_f); }
        return false;
    }
    virtual EVROverlayError SetOverlayIntersectionMask(VROverlayHandle_t ulOverlayHandle, VROverlayIntersectionMaskPrimitive_t *pMaskPrimitives, uint32_t unNumMaskPrimitives, uint32_t unPrimitiveSize = sizeof( VROverlayIntersectionMaskPrimitive_t )) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayIntersectionMask\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError TriggerLaserMouseHapticVibration(VROverlayHandle_t ulOverlayHandle, float fDurationSeconds, float fFrequency, float fAmplitude) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::TriggerLaserMouseHapticVibration\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlayCursor(VROverlayHandle_t ulOverlayHandle, VROverlayHandle_t ulCursorHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayCursor\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlayCursorPositionOverride(VROverlayHandle_t ulOverlayHandle, const HmdVector2_t *pvCursor) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayCursorPositionOverride\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError ClearOverlayCursorPositionOverride(VROverlayHandle_t ulOverlayHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::ClearOverlayCursorPositionOverride\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlayTexture(VROverlayHandle_t ulOverlayHandle, const Texture_t *pTexture) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayTexture\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError ClearOverlayTexture(VROverlayHandle_t ulOverlayHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::ClearOverlayTexture\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlayRaw(VROverlayHandle_t ulOverlayHandle, void *pvBuffer, uint32_t unWidth, uint32_t unHeight, uint32_t unBytesPerPixel) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayRaw\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError SetOverlayFromFile(VROverlayHandle_t ulOverlayHandle, const char *pchFilePath) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetOverlayFromFile\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetOverlayTexture(VROverlayHandle_t ulOverlayHandle, void **pNativeTextureHandle, void *pNativeTextureRef, uint32_t *pWidth, uint32_t *pHeight, uint32_t *pNativeFormat, ETextureType *pAPIType, EColorSpace *pColorSpace, VRTextureBounds_t *pTextureBounds) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayTexture\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError ReleaseNativeOverlayHandle(VROverlayHandle_t ulOverlayHandle, void *pNativeTextureHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::ReleaseNativeOverlayHandle\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetOverlayTextureSize(VROverlayHandle_t ulOverlayHandle, uint32_t *pWidth, uint32_t *pHeight) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetOverlayTextureSize\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError CreateDashboardOverlay(const char *pchOverlayKey, const char *pchOverlayFriendlyName, VROverlayHandle_t * pMainHandle, VROverlayHandle_t *pThumbnailHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::CreateDashboardOverlay\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual bool IsDashboardVisible() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::IsDashboardVisible\n"); fclose(_f); }
        return false;
    }
    virtual bool IsActiveDashboardOverlay(VROverlayHandle_t ulOverlayHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::IsActiveDashboardOverlay\n"); fclose(_f); }
        return false;
    }
    virtual EVROverlayError SetDashboardOverlaySceneProcess(VROverlayHandle_t ulOverlayHandle, uint32_t unProcessId) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetDashboardOverlaySceneProcess\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError GetDashboardOverlaySceneProcess(VROverlayHandle_t ulOverlayHandle, uint32_t *punProcessId) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetDashboardOverlaySceneProcess\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual void ShowDashboard(const char *pchOverlayToShow) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::ShowDashboard\n"); fclose(_f); }
    }
    virtual vr::TrackedDeviceIndex_t GetPrimaryDashboardDevice() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetPrimaryDashboardDevice\n"); fclose(_f); }
        return (vr::TrackedDeviceIndex_t)0;
    }
    virtual EVROverlayError ShowKeyboard(EGamepadTextInputMode eInputMode, EGamepadTextInputLineMode eLineInputMode, uint32_t unFlags, const char *pchDescription, uint32_t unCharMax, const char *pchExistingText, uint64_t uUserValue) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::ShowKeyboard\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError ShowKeyboardForOverlay(VROverlayHandle_t ulOverlayHandle, EGamepadTextInputMode eInputMode, EGamepadTextInputLineMode eLineInputMode, uint32_t unFlags, const char *pchDescription, uint32_t unCharMax, const char *pchExistingText, uint64_t uUserValue) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::ShowKeyboardForOverlay\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual uint32_t GetKeyboardText(VR_OUT_STRING() char *pchText, uint32_t cchText) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::GetKeyboardText\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual void HideKeyboard() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::HideKeyboard\n"); fclose(_f); }
    }
    virtual void SetKeyboardTransformAbsolute(ETrackingUniverseOrigin eTrackingOrigin, const HmdMatrix34_t *pmatTrackingOriginToKeyboardTransform) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetKeyboardTransformAbsolute\n"); fclose(_f); }
    }
    virtual void SetKeyboardPositionForOverlay(VROverlayHandle_t ulOverlayHandle, HmdRect2_t avoidRect) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::SetKeyboardPositionForOverlay\n"); fclose(_f); }
    }
    virtual VRMessageOverlayResponse ShowMessageOverlay(const char* pchText, const char* pchCaption, const char* pchButton0Text, const char* pchButton1Text = nullptr, const char* pchButton2Text = nullptr, const char* pchButton3Text = nullptr) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::ShowMessageOverlay\n"); fclose(_f); }
        return (VRMessageOverlayResponse)0;
    }
    virtual void CloseMessageOverlay() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlay::CloseMessageOverlay\n"); fclose(_f); }
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockOverlay;

class Mock_IVROverlayView : public vr::IVROverlayView {
public:
    virtual EVROverlayError AcquireOverlayView(VROverlayHandle_t ulOverlayHandle, VRNativeDevice_t *pNativeDevice, VROverlayView_t *pOverlayView, uint32_t unOverlayViewSize) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlayView::AcquireOverlayView\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual EVROverlayError ReleaseOverlayView(VROverlayView_t *pOverlayView) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlayView::ReleaseOverlayView\n"); fclose(_f); }
        return vr::VROverlayError_UnknownOverlay;
    }
    virtual void PostOverlayEvent(VROverlayHandle_t ulOverlayHandle, const VREvent_t *pvrEvent) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlayView::PostOverlayEvent\n"); fclose(_f); }
    }
    virtual bool IsViewingPermitted(VROverlayHandle_t ulOverlayHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVROverlayView::IsViewingPermitted\n"); fclose(_f); }
        return false;
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockOverlayView;

class Mock_IVRRenderModels : public vr::IVRRenderModels {
public:
    virtual EVRRenderModelError LoadRenderModel_Async(const char *pchRenderModelName, RenderModel_t **ppRenderModel) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::LoadRenderModel_Async\n"); fclose(_f); }
        return vr::VRRenderModelError_NotSupported;
    }
    virtual void FreeRenderModel(RenderModel_t *pRenderModel) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::FreeRenderModel\n"); fclose(_f); }
    }
    virtual EVRRenderModelError LoadTexture_Async(TextureID_t textureId, RenderModel_TextureMap_t **ppTexture) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::LoadTexture_Async\n"); fclose(_f); }
        return vr::VRRenderModelError_NotSupported;
    }
    virtual void FreeTexture(RenderModel_TextureMap_t *pTexture) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::FreeTexture\n"); fclose(_f); }
    }
    virtual EVRRenderModelError LoadTextureD3D11_Async(TextureID_t textureId, void *pD3D11Device, void **ppD3D11Texture2D) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::LoadTextureD3D11_Async\n"); fclose(_f); }
        return vr::VRRenderModelError_NotSupported;
    }
    virtual EVRRenderModelError LoadIntoTextureD3D11_Async(TextureID_t textureId, void *pDstTexture) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::LoadIntoTextureD3D11_Async\n"); fclose(_f); }
        return vr::VRRenderModelError_NotSupported;
    }
    virtual void FreeTextureD3D11(void *pD3D11Texture2D) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::FreeTextureD3D11\n"); fclose(_f); }
    }
    virtual uint32_t GetRenderModelName(uint32_t unRenderModelIndex, VR_OUT_STRING() char *pchRenderModelName, uint32_t unRenderModelNameLen) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::GetRenderModelName\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual uint32_t GetRenderModelCount() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::GetRenderModelCount\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual uint32_t GetComponentCount(const char *pchRenderModelName) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::GetComponentCount\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual uint32_t GetComponentName(const char *pchRenderModelName, uint32_t unComponentIndex, VR_OUT_STRING( ) char *pchComponentName, uint32_t unComponentNameLen) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::GetComponentName\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual uint64_t GetComponentButtonMask(const char *pchRenderModelName, const char *pchComponentName) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::GetComponentButtonMask\n"); fclose(_f); }
        return (uint64_t)0;
    }
    virtual uint32_t GetComponentRenderModelName(const char *pchRenderModelName, const char *pchComponentName, VR_OUT_STRING( ) char *pchComponentRenderModelName, uint32_t unComponentRenderModelNameLen) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::GetComponentRenderModelName\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual bool GetComponentStateForDevicePath(const char *pchRenderModelName, const char *pchComponentName, vr::VRInputValueHandle_t devicePath, const vr::RenderModel_ControllerMode_State_t *pState, vr::RenderModel_ComponentState_t *pComponentState) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::GetComponentStateForDevicePath\n"); fclose(_f); }
        return false;
    }
    virtual bool GetComponentState(const char *pchRenderModelName, const char *pchComponentName, const vr::VRControllerState_t *pControllerState, const RenderModel_ControllerMode_State_t *pState, RenderModel_ComponentState_t *pComponentState) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::GetComponentState\n"); fclose(_f); }
        return false;
    }
    virtual bool RenderModelHasComponent(const char *pchRenderModelName, const char *pchComponentName) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::RenderModelHasComponent\n"); fclose(_f); }
        return false;
    }
    virtual uint32_t GetRenderModelThumbnailURL(const char *pchRenderModelName, VR_OUT_STRING() char *pchThumbnailURL, uint32_t unThumbnailURLLen, vr::EVRRenderModelError *peError) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::GetRenderModelThumbnailURL\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual uint32_t GetRenderModelOriginalPath(const char *pchRenderModelName, VR_OUT_STRING() char *pchOriginalPath, uint32_t unOriginalPathLen, vr::EVRRenderModelError *peError) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::GetRenderModelOriginalPath\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual const char * GetRenderModelErrorNameFromEnum(vr::EVRRenderModelError error) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRRenderModels::GetRenderModelErrorNameFromEnum\n"); fclose(_f); }
        return "1.10.30";
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockRenderModels;

class Mock_IVRExtendedDisplay : public vr::IVRExtendedDisplay {
public:
    virtual void GetWindowBounds(int32_t *pnX, int32_t *pnY, uint32_t *pnWidth, uint32_t *pnHeight) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRExtendedDisplay::GetWindowBounds\n"); fclose(_f); }
    }
    virtual void GetEyeOutputViewport(EVREye eEye, uint32_t *pnX, uint32_t *pnY, uint32_t *pnWidth, uint32_t *pnHeight) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRExtendedDisplay::GetEyeOutputViewport\n"); fclose(_f); }
        if(pnX) *pnX = 0; if(pnY) *pnY = 0; if(pnWidth) *pnWidth = 1920; if(pnHeight) *pnHeight = 1080;
    }
    virtual void GetDXGIOutputInfo(int32_t *pnAdapterIndex, int32_t *pnAdapterOutputIndex) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRExtendedDisplay::GetDXGIOutputInfo\n"); fclose(_f); }
        if(pnAdapterIndex) *pnAdapterIndex = 0;
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockExtendedDisplay;

class Mock_IVRTrackedCamera : public vr::IVRTrackedCamera {
public:
    virtual const char * GetCameraErrorNameFromEnum(vr::EVRTrackedCameraError eCameraError) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRTrackedCamera::GetCameraErrorNameFromEnum\n"); fclose(_f); }
        return "1.10.30";
    }
    virtual vr::EVRTrackedCameraError HasCamera(vr::TrackedDeviceIndex_t nDeviceIndex, bool *pHasCamera) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRTrackedCamera::HasCamera\n"); fclose(_f); }
        return vr::VRTrackedCameraError_OperationFailed;
    }
    virtual vr::EVRTrackedCameraError GetCameraFrameSize(vr::TrackedDeviceIndex_t nDeviceIndex, vr::EVRTrackedCameraFrameType eFrameType, uint32_t *pnWidth, uint32_t *pnHeight, uint32_t *pnFrameBufferSize) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRTrackedCamera::GetCameraFrameSize\n"); fclose(_f); }
        return vr::VRTrackedCameraError_OperationFailed;
    }
    virtual vr::EVRTrackedCameraError GetCameraIntrinsics(vr::TrackedDeviceIndex_t nDeviceIndex, uint32_t nCameraIndex, vr::EVRTrackedCameraFrameType eFrameType, vr::HmdVector2_t *pFocalLength, vr::HmdVector2_t *pCenter) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRTrackedCamera::GetCameraIntrinsics\n"); fclose(_f); }
        return vr::VRTrackedCameraError_OperationFailed;
    }
    virtual vr::EVRTrackedCameraError GetCameraProjection(vr::TrackedDeviceIndex_t nDeviceIndex, uint32_t nCameraIndex, vr::EVRTrackedCameraFrameType eFrameType, float flZNear, float flZFar, vr::HmdMatrix44_t *pProjection) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRTrackedCamera::GetCameraProjection\n"); fclose(_f); }
        return vr::VRTrackedCameraError_OperationFailed;
    }
    virtual vr::EVRTrackedCameraError AcquireVideoStreamingService(vr::TrackedDeviceIndex_t nDeviceIndex, vr::TrackedCameraHandle_t *pHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRTrackedCamera::AcquireVideoStreamingService\n"); fclose(_f); }
        return vr::VRTrackedCameraError_OperationFailed;
    }
    virtual vr::EVRTrackedCameraError ReleaseVideoStreamingService(vr::TrackedCameraHandle_t hTrackedCamera) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRTrackedCamera::ReleaseVideoStreamingService\n"); fclose(_f); }
        return vr::VRTrackedCameraError_OperationFailed;
    }
    virtual vr::EVRTrackedCameraError GetVideoStreamFrameBuffer(vr::TrackedCameraHandle_t hTrackedCamera, vr::EVRTrackedCameraFrameType eFrameType, void *pFrameBuffer, uint32_t nFrameBufferSize, vr::CameraVideoStreamFrameHeader_t *pFrameHeader, uint32_t nFrameHeaderSize) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRTrackedCamera::GetVideoStreamFrameBuffer\n"); fclose(_f); }
        return vr::VRTrackedCameraError_OperationFailed;
    }
    virtual vr::EVRTrackedCameraError GetVideoStreamTextureSize(vr::TrackedDeviceIndex_t nDeviceIndex, vr::EVRTrackedCameraFrameType eFrameType, vr::VRTextureBounds_t *pTextureBounds, uint32_t *pnWidth, uint32_t *pnHeight) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRTrackedCamera::GetVideoStreamTextureSize\n"); fclose(_f); }
        return vr::VRTrackedCameraError_OperationFailed;
    }
    virtual vr::EVRTrackedCameraError GetVideoStreamTextureD3D11(vr::TrackedCameraHandle_t hTrackedCamera, vr::EVRTrackedCameraFrameType eFrameType, void *pD3D11DeviceOrResource, void **ppD3D11ShaderResourceView, vr::CameraVideoStreamFrameHeader_t *pFrameHeader, uint32_t nFrameHeaderSize) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRTrackedCamera::GetVideoStreamTextureD3D11\n"); fclose(_f); }
        return vr::VRTrackedCameraError_OperationFailed;
    }
    virtual vr::EVRTrackedCameraError GetVideoStreamTextureGL(vr::TrackedCameraHandle_t hTrackedCamera, vr::EVRTrackedCameraFrameType eFrameType, vr::glUInt_t *pglTextureId, vr::CameraVideoStreamFrameHeader_t *pFrameHeader, uint32_t nFrameHeaderSize) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRTrackedCamera::GetVideoStreamTextureGL\n"); fclose(_f); }
        return vr::VRTrackedCameraError_OperationFailed;
    }
    virtual vr::EVRTrackedCameraError ReleaseVideoStreamTextureGL(vr::TrackedCameraHandle_t hTrackedCamera, vr::glUInt_t glTextureId) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRTrackedCamera::ReleaseVideoStreamTextureGL\n"); fclose(_f); }
        return vr::VRTrackedCameraError_OperationFailed;
    }
    virtual void SetCameraTrackingSpace(vr::ETrackingUniverseOrigin eUniverse) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRTrackedCamera::SetCameraTrackingSpace\n"); fclose(_f); }
    }
    virtual vr::ETrackingUniverseOrigin GetCameraTrackingSpace() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRTrackedCamera::GetCameraTrackingSpace\n"); fclose(_f); }
        return (vr::ETrackingUniverseOrigin)0;
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockTrackedCamera;

class Mock_IVRScreenshots : public vr::IVRScreenshots {
public:
    virtual vr::EVRScreenshotError RequestScreenshot(vr::ScreenshotHandle_t *pOutScreenshotHandle, vr::EVRScreenshotType type, const char *pchPreviewFilename, const char *pchVRFilename) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRScreenshots::RequestScreenshot\n"); fclose(_f); }
        return (vr::EVRScreenshotError)1;
    }
    virtual vr::EVRScreenshotError HookScreenshot(VR_ARRAY_COUNT( numTypes ) const vr::EVRScreenshotType *pSupportedTypes, int numTypes) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRScreenshots::HookScreenshot\n"); fclose(_f); }
        return (vr::EVRScreenshotError)1;
    }
    virtual vr::EVRScreenshotType GetScreenshotPropertyType(vr::ScreenshotHandle_t screenshotHandle, vr::EVRScreenshotError *pError) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRScreenshots::GetScreenshotPropertyType\n"); fclose(_f); }
        return (vr::EVRScreenshotType)0;
    }
    virtual uint32_t GetScreenshotPropertyFilename(vr::ScreenshotHandle_t screenshotHandle, vr::EVRScreenshotPropertyFilenames filenameType, VR_OUT_STRING() char *pchFilename, uint32_t cchFilename, vr::EVRScreenshotError *pError) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRScreenshots::GetScreenshotPropertyFilename\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual vr::EVRScreenshotError UpdateScreenshotProgress(vr::ScreenshotHandle_t screenshotHandle, float flProgress) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRScreenshots::UpdateScreenshotProgress\n"); fclose(_f); }
        return (vr::EVRScreenshotError)1;
    }
    virtual vr::EVRScreenshotError TakeStereoScreenshot(vr::ScreenshotHandle_t *pOutScreenshotHandle, const char *pchPreviewFilename, const char *pchVRFilename) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRScreenshots::TakeStereoScreenshot\n"); fclose(_f); }
        return (vr::EVRScreenshotError)1;
    }
    virtual vr::EVRScreenshotError SubmitScreenshot(vr::ScreenshotHandle_t screenshotHandle, vr::EVRScreenshotType type, const char *pchSourcePreviewFilename, const char *pchSourceVRFilename) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRScreenshots::SubmitScreenshot\n"); fclose(_f); }
        return (vr::EVRScreenshotError)1;
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockScreenshots;

class Mock_IVRResources : public vr::IVRResources {
public:
    virtual uint32_t LoadSharedResource(const char *pchResourceName, char *pchBuffer, uint32_t unBufferLen) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRResources::LoadSharedResource\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual uint32_t GetResourceFullPath(const char *pchResourceName, const char *pchResourceTypeDirectory, VR_OUT_STRING() char *pchPathBuffer, uint32_t unBufferLen) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRResources::GetResourceFullPath\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockResources;

class Mock_IVRDriverManager : public vr::IVRDriverManager {
public:
    virtual uint32_t GetDriverCount() const override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRDriverManager::GetDriverCount\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual uint32_t GetDriverName(vr::DriverId_t nDriver, VR_OUT_STRING() char *pchValue, uint32_t unBufferSize) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRDriverManager::GetDriverName\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual DriverHandle_t GetDriverHandle(const char *pchDriverName) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRDriverManager::GetDriverHandle\n"); fclose(_f); }
        return (DriverHandle_t)0;
    }
    virtual bool IsEnabled(vr::DriverId_t nDriver) const override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRDriverManager::IsEnabled\n"); fclose(_f); }
        return false;
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockDriverManager;

class Mock_IVRInput : public vr::IVRInput {
public:
    virtual EVRInputError SetActionManifestPath(const char *pchActionManifestPath) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::SetActionManifestPath\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual EVRInputError GetActionSetHandle(const char *pchActionSetName, VRActionSetHandle_t *pHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetActionSetHandle\n"); fclose(_f); }
        static uint64_t nextSetHandle = 1000;
        if(pHandle) *pHandle = nextSetHandle++;
        return vr::VRInputError_None;
    }
    virtual EVRInputError GetActionHandle(const char *pchActionName, VRActionHandle_t *pHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetActionHandle\n"); fclose(_f); }
        static uint64_t nextHandle = 10;
        if(pHandle) { *pHandle = nextHandle++; }
        return vr::VRInputError_None;
    }
    virtual EVRInputError GetInputSourceHandle(const char *pchInputSourcePath, VRInputValueHandle_t *pHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetInputSourceHandle\n"); fclose(_f); }
        static uint64_t nextSourceHandle = 10000;
        if(pHandle) { *pHandle = nextSourceHandle++; if(pchInputSourcePath) { if(strstr(pchInputSourcePath, "left")) *pHandle = 1; else if(strstr(pchInputSourcePath, "right")) *pHandle = 2; } }
        return vr::VRInputError_None;
    }
    virtual EVRInputError UpdateActionState(VR_ARRAY_COUNT( unSetCount ) VRActiveActionSet_t *pSets, uint32_t unSizeOfVRSelectedActionSet_t, uint32_t unSetCount) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::UpdateActionState\n"); fclose(_f); }
        return vr::VRInputError_None;
    }
    virtual EVRInputError GetDigitalActionData(VRActionHandle_t action, InputDigitalActionData_t *pActionData, uint32_t unActionDataSize, VRInputValueHandle_t ulRestrictToDevice) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetDigitalActionData\n"); fclose(_f); }
        if(pActionData && unActionDataSize > 0) {
            vr::InputDigitalActionData_t temp = {0};
            temp.bActive = true;
            if (pSharedHands) {
                bool pressed = false;
                if (ulRestrictToDevice == 1) pressed = pSharedHands->leftPinch;
                else if (ulRestrictToDevice == 2) pressed = pSharedHands->rightPinch;
                else pressed = pSharedHands->leftPinch || pSharedHands->rightPinch;
                temp.bState = pressed;
            }
            memcpy(pActionData, &temp, unActionDataSize > sizeof(temp) ? sizeof(temp) : unActionDataSize);
        }
        return vr::VRInputError_None;
    }
    virtual EVRInputError GetAnalogActionData(VRActionHandle_t action, InputAnalogActionData_t *pActionData, uint32_t unActionDataSize, VRInputValueHandle_t ulRestrictToDevice) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetAnalogActionData\n"); fclose(_f); }
        if(pActionData && unActionDataSize > 0) {
            vr::InputAnalogActionData_t temp = {0};
            temp.bActive = true;
            memcpy(pActionData, &temp, unActionDataSize > sizeof(temp) ? sizeof(temp) : unActionDataSize);
        }
        return vr::VRInputError_None;
    }
    virtual EVRInputError GetPoseActionDataRelativeToNow(VRActionHandle_t action, ETrackingUniverseOrigin eOrigin, float fPredictedSecondsFromNow, InputPoseActionData_t *pActionData, uint32_t unActionDataSize, VRInputValueHandle_t ulRestrictToDevice) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetPoseActionDataRelativeToNow\n"); fclose(_f); }
        if(pActionData && unActionDataSize > 0) {
            vr::InputPoseActionData_t temp = {0};
            temp.bActive = true;
            temp.pose.bPoseIsValid = true;
            temp.pose.bDeviceIsConnected = true;
            temp.pose.eTrackingResult = vr::TrackingResult_Running_OK;
            temp.pose.mDeviceToAbsoluteTracking.m[0][0] = 1; temp.pose.mDeviceToAbsoluteTracking.m[1][1] = 1; temp.pose.mDeviceToAbsoluteTracking.m[2][2] = 1;
            memcpy(pActionData, &temp, unActionDataSize > sizeof(temp) ? sizeof(temp) : unActionDataSize);
        }
        return vr::VRInputError_None;
    }
    virtual EVRInputError GetPoseActionDataForNextFrame(VRActionHandle_t action, ETrackingUniverseOrigin eOrigin, InputPoseActionData_t *pActionData, uint32_t unActionDataSize, VRInputValueHandle_t ulRestrictToDevice) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetPoseActionDataForNextFrame\n"); fclose(_f); }
        if(pActionData && unActionDataSize > 0) {
            vr::InputPoseActionData_t temp = {0};
            temp.bActive = true;
            temp.pose.bPoseIsValid = true;
            temp.pose.bDeviceIsConnected = true;
            temp.pose.eTrackingResult = vr::TrackingResult_Running_OK;
            temp.pose.mDeviceToAbsoluteTracking.m[0][0] = 1; temp.pose.mDeviceToAbsoluteTracking.m[1][1] = 1; temp.pose.mDeviceToAbsoluteTracking.m[2][2] = 1;
            memcpy(pActionData, &temp, unActionDataSize > sizeof(temp) ? sizeof(temp) : unActionDataSize);
        }
        return vr::VRInputError_None;
    }
    virtual EVRInputError GetSkeletalActionData(VRActionHandle_t action, InputSkeletalActionData_t *pActionData, uint32_t unActionDataSize) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetSkeletalActionData\n"); fclose(_f); }
        if(pActionData && unActionDataSize > 0) {
            vr::InputSkeletalActionData_t temp = {0};
            temp.bActive = false;
            memcpy(pActionData, &temp, unActionDataSize > sizeof(temp) ? sizeof(temp) : unActionDataSize);
        }
        return vr::VRInputError_None;
    }
    virtual EVRInputError GetDominantHand(ETrackedControllerRole *peDominantHand) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetDominantHand\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual EVRInputError SetDominantHand(ETrackedControllerRole eDominantHand) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::SetDominantHand\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual EVRInputError GetBoneCount(VRActionHandle_t action, uint32_t* pBoneCount) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetBoneCount\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual EVRInputError GetBoneHierarchy(VRActionHandle_t action, VR_ARRAY_COUNT( unIndexArayCount ) BoneIndex_t* pParentIndices, uint32_t unIndexArayCount) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetBoneHierarchy\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual EVRInputError GetBoneName(VRActionHandle_t action, BoneIndex_t nBoneIndex, VR_OUT_STRING() char* pchBoneName, uint32_t unNameBufferSize) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetBoneName\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual EVRInputError GetSkeletalReferenceTransforms(VRActionHandle_t action, EVRSkeletalTransformSpace eTransformSpace, EVRSkeletalReferencePose eReferencePose, VR_ARRAY_COUNT( unTransformArrayCount ) VRBoneTransform_t *pTransformArray, uint32_t unTransformArrayCount) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetSkeletalReferenceTransforms\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual EVRInputError GetSkeletalTrackingLevel(VRActionHandle_t action, EVRSkeletalTrackingLevel* pSkeletalTrackingLevel) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetSkeletalTrackingLevel\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual EVRInputError GetSkeletalBoneData(VRActionHandle_t action, EVRSkeletalTransformSpace eTransformSpace, EVRSkeletalMotionRange eMotionRange, VR_ARRAY_COUNT( unTransformArrayCount ) VRBoneTransform_t *pTransformArray, uint32_t unTransformArrayCount) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetSkeletalBoneData\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual EVRInputError GetSkeletalSummaryData(VRActionHandle_t action, EVRSummaryType eSummaryType, VRSkeletalSummaryData_t * pSkeletalSummaryData) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetSkeletalSummaryData\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual EVRInputError GetSkeletalBoneDataCompressed(VRActionHandle_t action, EVRSkeletalMotionRange eMotionRange, VR_OUT_BUFFER_COUNT( unCompressedSize ) void *pvCompressedData, uint32_t unCompressedSize, uint32_t *punRequiredCompressedSize) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetSkeletalBoneDataCompressed\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual EVRInputError DecompressSkeletalBoneData(const void *pvCompressedBuffer, uint32_t unCompressedBufferSize, EVRSkeletalTransformSpace eTransformSpace, VR_ARRAY_COUNT( unTransformArrayCount ) VRBoneTransform_t *pTransformArray, uint32_t unTransformArrayCount) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::DecompressSkeletalBoneData\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual EVRInputError TriggerHapticVibrationAction(VRActionHandle_t action, float fStartSecondsFromNow, float fDurationSeconds, float fFrequency, float fAmplitude, VRInputValueHandle_t ulRestrictToDevice) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::TriggerHapticVibrationAction\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual EVRInputError GetActionOrigins(VRActionSetHandle_t actionSetHandle, VRActionHandle_t digitalActionHandle, VR_ARRAY_COUNT( originOutCount ) VRInputValueHandle_t *originsOut, uint32_t originOutCount) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetActionOrigins\n"); fclose(_f); }
        if(originsOut && originOutCount > 0) { memset(originsOut, 0, sizeof(vr::VRInputValueHandle_t) * originOutCount); originsOut[0] = actionSetHandle; }
        return vr::VRInputError_None;
    }
    virtual EVRInputError GetOriginLocalizedName(VRInputValueHandle_t origin, VR_OUT_STRING() char *pchNameArray, uint32_t unNameArraySize, int32_t unStringSectionsToInclude) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetOriginLocalizedName\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual EVRInputError GetOriginTrackedDeviceInfo(VRInputValueHandle_t origin, InputOriginInfo_t *pOriginInfo, uint32_t unOriginInfoSize) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetOriginTrackedDeviceInfo\n"); fclose(_f); }
        if(pOriginInfo && unOriginInfoSize > 0) {
            vr::InputOriginInfo_t temp = {0};
            temp.devicePath = origin;
            temp.trackedDeviceIndex = (origin == 1) ? 1 : 2;
            memcpy(pOriginInfo, &temp, unOriginInfoSize > sizeof(temp) ? sizeof(temp) : unOriginInfoSize);
        }
        return vr::VRInputError_None;
    }
    virtual EVRInputError GetActionBindingInfo(VRActionHandle_t action, InputBindingInfo_t *pOriginInfo, uint32_t unBindingInfoSize, uint32_t unBindingInfoCount, uint32_t *punReturnedBindingInfoCount) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetActionBindingInfo\n"); fclose(_f); }
        if(pOriginInfo && unBindingInfoSize > 0 && unBindingInfoCount > 0) {
            memset(pOriginInfo, 0, unBindingInfoSize * unBindingInfoCount);
        }
        if(punReturnedBindingInfoCount) *punReturnedBindingInfoCount = 0;
        return vr::VRInputError_None;
    }
    virtual EVRInputError ShowActionOrigins(VRActionSetHandle_t actionSetHandle, VRActionHandle_t ulActionHandle) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::ShowActionOrigins\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual EVRInputError ShowBindingsForActionSet(VR_ARRAY_COUNT( unSetCount ) VRActiveActionSet_t *pSets, uint32_t unSizeOfVRSelectedActionSet_t, uint32_t unSetCount, VRInputValueHandle_t originToHighlight) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::ShowBindingsForActionSet\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual EVRInputError GetComponentStateForBinding(const char *pchRenderModelName, const char *pchComponentName, const InputBindingInfo_t *pOriginInfo, uint32_t unBindingInfoSize, uint32_t unBindingInfoCount, vr::RenderModel_ComponentState_t *pComponentState) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetComponentStateForBinding\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual bool IsUsingLegacyInput() override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::IsUsingLegacyInput\n"); fclose(_f); }
        return false;
    }
    virtual EVRInputError OpenBindingUI(const char* pchAppKey, VRActionSetHandle_t ulActionSetHandle, VRInputValueHandle_t ulDeviceHandle, bool bShowOnDesktop) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::OpenBindingUI\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual EVRInputError GetBindingVariant(vr::VRInputValueHandle_t ulDevicePath, VR_OUT_STRING() char *pchVariantArray, uint32_t unVariantArraySize) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRInput::GetBindingVariant\n"); fclose(_f); }
        return vr::VRInputError_InvalidHandle;
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockInput;

class Mock_IVRIOBuffer : public vr::IVRIOBuffer {
public:
    virtual vr::EIOBufferError Open(const char *pchPath, vr::EIOBufferMode mode, uint32_t unElementSize, uint32_t unElements, vr::IOBufferHandle_t *pulBuffer) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRIOBuffer::Open\n"); fclose(_f); }
        return (vr::EIOBufferError)1;
    }
    virtual vr::EIOBufferError Close(vr::IOBufferHandle_t ulBuffer) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRIOBuffer::Close\n"); fclose(_f); }
        return (vr::EIOBufferError)1;
    }
    virtual vr::EIOBufferError Read(vr::IOBufferHandle_t ulBuffer, void *pDst, uint32_t unBytes, uint32_t *punRead) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRIOBuffer::Read\n"); fclose(_f); }
        return (vr::EIOBufferError)1;
    }
    virtual vr::EIOBufferError Write(vr::IOBufferHandle_t ulBuffer, void *pSrc, uint32_t unBytes) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRIOBuffer::Write\n"); fclose(_f); }
        return (vr::EIOBufferError)1;
    }
    virtual vr::PropertyContainerHandle_t PropertyContainer(vr::IOBufferHandle_t ulBuffer) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRIOBuffer::PropertyContainer\n"); fclose(_f); }
        return (vr::PropertyContainerHandle_t)0;
    }
    virtual bool HasReaders(vr::IOBufferHandle_t ulBuffer) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRIOBuffer::HasReaders\n"); fclose(_f); }
        return false;
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockIOBuffer;

class Mock_IVRSpatialAnchors : public vr::IVRSpatialAnchors {
public:
    virtual EVRSpatialAnchorError CreateSpatialAnchorFromDescriptor(const char *pchDescriptor, SpatialAnchorHandle_t *pHandleOut) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSpatialAnchors::CreateSpatialAnchorFromDescriptor\n"); fclose(_f); }
        return (EVRSpatialAnchorError)1;
    }
    virtual EVRSpatialAnchorError CreateSpatialAnchorFromPose(TrackedDeviceIndex_t unDeviceIndex, ETrackingUniverseOrigin eOrigin, SpatialAnchorPose_t *pPose, SpatialAnchorHandle_t *pHandleOut) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSpatialAnchors::CreateSpatialAnchorFromPose\n"); fclose(_f); }
        return (EVRSpatialAnchorError)1;
    }
    virtual EVRSpatialAnchorError GetSpatialAnchorPose(SpatialAnchorHandle_t unHandle, ETrackingUniverseOrigin eOrigin, SpatialAnchorPose_t *pPoseOut) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSpatialAnchors::GetSpatialAnchorPose\n"); fclose(_f); }
        return (EVRSpatialAnchorError)1;
    }
    virtual EVRSpatialAnchorError GetSpatialAnchorDescriptor(SpatialAnchorHandle_t unHandle, VR_OUT_STRING() char *pchDescriptorOut, uint32_t *punDescriptorBufferLenInOut) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRSpatialAnchors::GetSpatialAnchorDescriptor\n"); fclose(_f); }
        return (EVRSpatialAnchorError)1;
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockSpatialAnchors;

class Mock_IVRDebug : public vr::IVRDebug {
public:
    virtual EVRDebugError EmitVrProfilerEvent(const char *pchMessage) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRDebug::EmitVrProfilerEvent\n"); fclose(_f); }
        return (EVRDebugError)1;
    }
    virtual EVRDebugError BeginVrProfilerEvent(VrProfilerEventHandle_t *pHandleOut) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRDebug::BeginVrProfilerEvent\n"); fclose(_f); }
        return (EVRDebugError)1;
    }
    virtual EVRDebugError FinishVrProfilerEvent(VrProfilerEventHandle_t hHandle, const char *pchMessage) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRDebug::FinishVrProfilerEvent\n"); fclose(_f); }
        return (EVRDebugError)1;
    }
    virtual uint32_t DriverDebugRequest(vr::TrackedDeviceIndex_t unDeviceIndex, const char *pchRequest, VR_OUT_STRING() char *pchResponseBuffer, uint32_t unResponseBufferSize) override {
        FILE* _f = fopen("vr_emulator_log.txt", "a"); if(_f) { fprintf(_f, "Called: IVRDebug::DriverDebugRequest\n"); fclose(_f); }
        return (uint32_t)0;
    }
    virtual void* DummyPadding0() { return nullptr; }
    virtual void* DummyPadding1() { return nullptr; }
    virtual void* DummyPadding2() { return nullptr; }
    virtual void* DummyPadding3() { return nullptr; }
    virtual void* DummyPadding4() { return nullptr; }
    virtual void* DummyPadding5() { return nullptr; }
    virtual void* DummyPadding6() { return nullptr; }
    virtual void* DummyPadding7() { return nullptr; }
    virtual void* DummyPadding8() { return nullptr; }
    virtual void* DummyPadding9() { return nullptr; }
    virtual void* DummyPadding10() { return nullptr; }
    virtual void* DummyPadding11() { return nullptr; }
    virtual void* DummyPadding12() { return nullptr; }
    virtual void* DummyPadding13() { return nullptr; }
    virtual void* DummyPadding14() { return nullptr; }
    virtual void* DummyPadding15() { return nullptr; }
    virtual void* DummyPadding16() { return nullptr; }
    virtual void* DummyPadding17() { return nullptr; }
    virtual void* DummyPadding18() { return nullptr; }
    virtual void* DummyPadding19() { return nullptr; }
    virtual void* DummyPadding20() { return nullptr; }
    virtual void* DummyPadding21() { return nullptr; }
    virtual void* DummyPadding22() { return nullptr; }
    virtual void* DummyPadding23() { return nullptr; }
    virtual void* DummyPadding24() { return nullptr; }
    virtual void* DummyPadding25() { return nullptr; }
    virtual void* DummyPadding26() { return nullptr; }
    virtual void* DummyPadding27() { return nullptr; }
    virtual void* DummyPadding28() { return nullptr; }
    virtual void* DummyPadding29() { return nullptr; }
    virtual void* DummyPadding30() { return nullptr; }
    virtual void* DummyPadding31() { return nullptr; }
    virtual void* DummyPadding32() { return nullptr; }
    virtual void* DummyPadding33() { return nullptr; }
    virtual void* DummyPadding34() { return nullptr; }
    virtual void* DummyPadding35() { return nullptr; }
    virtual void* DummyPadding36() { return nullptr; }
    virtual void* DummyPadding37() { return nullptr; }
    virtual void* DummyPadding38() { return nullptr; }
    virtual void* DummyPadding39() { return nullptr; }
    virtual void* DummyPadding40() { return nullptr; }
    virtual void* DummyPadding41() { return nullptr; }
    virtual void* DummyPadding42() { return nullptr; }
    virtual void* DummyPadding43() { return nullptr; }
    virtual void* DummyPadding44() { return nullptr; }
    virtual void* DummyPadding45() { return nullptr; }
    virtual void* DummyPadding46() { return nullptr; }
    virtual void* DummyPadding47() { return nullptr; }
    virtual void* DummyPadding48() { return nullptr; }
    virtual void* DummyPadding49() { return nullptr; }
    virtual void* DummyPadding50() { return nullptr; }
    virtual void* DummyPadding51() { return nullptr; }
    virtual void* DummyPadding52() { return nullptr; }
    virtual void* DummyPadding53() { return nullptr; }
    virtual void* DummyPadding54() { return nullptr; }
    virtual void* DummyPadding55() { return nullptr; }
    virtual void* DummyPadding56() { return nullptr; }
    virtual void* DummyPadding57() { return nullptr; }
    virtual void* DummyPadding58() { return nullptr; }
    virtual void* DummyPadding59() { return nullptr; }
    virtual void* DummyPadding60() { return nullptr; }
    virtual void* DummyPadding61() { return nullptr; }
    virtual void* DummyPadding62() { return nullptr; }
    virtual void* DummyPadding63() { return nullptr; }
    virtual void* DummyPadding64() { return nullptr; }
    virtual void* DummyPadding65() { return nullptr; }
    virtual void* DummyPadding66() { return nullptr; }
    virtual void* DummyPadding67() { return nullptr; }
    virtual void* DummyPadding68() { return nullptr; }
    virtual void* DummyPadding69() { return nullptr; }
    virtual void* DummyPadding70() { return nullptr; }
    virtual void* DummyPadding71() { return nullptr; }
    virtual void* DummyPadding72() { return nullptr; }
    virtual void* DummyPadding73() { return nullptr; }
    virtual void* DummyPadding74() { return nullptr; }
    virtual void* DummyPadding75() { return nullptr; }
    virtual void* DummyPadding76() { return nullptr; }
    virtual void* DummyPadding77() { return nullptr; }
    virtual void* DummyPadding78() { return nullptr; }
    virtual void* DummyPadding79() { return nullptr; }
    virtual void* DummyPadding80() { return nullptr; }
    virtual void* DummyPadding81() { return nullptr; }
    virtual void* DummyPadding82() { return nullptr; }
    virtual void* DummyPadding83() { return nullptr; }
    virtual void* DummyPadding84() { return nullptr; }
    virtual void* DummyPadding85() { return nullptr; }
    virtual void* DummyPadding86() { return nullptr; }
    virtual void* DummyPadding87() { return nullptr; }
    virtual void* DummyPadding88() { return nullptr; }
    virtual void* DummyPadding89() { return nullptr; }
    virtual void* DummyPadding90() { return nullptr; }
    virtual void* DummyPadding91() { return nullptr; }
    virtual void* DummyPadding92() { return nullptr; }
    virtual void* DummyPadding93() { return nullptr; }
    virtual void* DummyPadding94() { return nullptr; }
    virtual void* DummyPadding95() { return nullptr; }
    virtual void* DummyPadding96() { return nullptr; }
    virtual void* DummyPadding97() { return nullptr; }
    virtual void* DummyPadding98() { return nullptr; }
    virtual void* DummyPadding99() { return nullptr; }
} g_mockDebug;


extern "C" __declspec(dllexport) void* VR_GetGenericInterface(const char *pchInterfaceVersion, vr::EVRInitError *peError) {
    if (peError) *peError = vr::VRInitError_None;
    FILE* f = fopen("vr_emulator_log.txt", "a");
    if(f) { fprintf(f, "Requested interface: %s\n", pchInterfaceVersion); fclose(f); }

    if (strstr(pchInterfaceVersion, "IVRMailbox")) return &g_universalMock;

    if (strstr(pchInterfaceVersion, "System")) return &g_mockSystem;
    if (strstr(pchInterfaceVersion, "Applications")) return &g_mockApplications;
    if (strstr(pchInterfaceVersion, "Settings")) return &g_mockSettings;
    if (strstr(pchInterfaceVersion, "Chaperone")) return &g_mockChaperone;
    if (strstr(pchInterfaceVersion, "ChaperoneSetup")) return &g_mockChaperoneSetup;
    if (strstr(pchInterfaceVersion, "Compositor")) return &g_mockCompositor;
    if (strstr(pchInterfaceVersion, "HeadsetView")) return &g_mockHeadsetView;
    if (strstr(pchInterfaceVersion, "Notifications")) return &g_mockNotifications;
    if (strstr(pchInterfaceVersion, "Overlay")) return &g_mockOverlay;
    if (strstr(pchInterfaceVersion, "OverlayView")) return &g_mockOverlayView;
    if (strstr(pchInterfaceVersion, "RenderModels")) return &g_mockRenderModels;
    if (strstr(pchInterfaceVersion, "ExtendedDisplay")) return &g_mockExtendedDisplay;
    if (strstr(pchInterfaceVersion, "TrackedCamera")) return &g_mockTrackedCamera;
    if (strstr(pchInterfaceVersion, "Screenshots")) return &g_mockScreenshots;
    if (strstr(pchInterfaceVersion, "Resources")) return &g_mockResources;
    if (strstr(pchInterfaceVersion, "DriverManager")) return &g_mockDriverManager;
    if (strstr(pchInterfaceVersion, "Input")) return &g_mockInput;
    if (strstr(pchInterfaceVersion, "IOBuffer")) return &g_mockIOBuffer;
    if (strstr(pchInterfaceVersion, "SpatialAnchors")) return &g_mockSpatialAnchors;
    if (strstr(pchInterfaceVersion, "Debug")) return &g_mockDebug;

    return nullptr;
}

extern "C" __declspec(dllexport) uint32_t VR_InitInternal2(vr::EVRInitError *peError, vr::EVRApplicationType eType, const char *pStartupInfo) {
    if (peError) *peError = vr::VRInitError_None;
    InitSharedMemory();
    return 1;
}

extern "C" __declspec(dllexport) void VR_ShutdownInternal() {
}

extern "C" __declspec(dllexport) bool VR_IsHmdPresent() {
    return true;
}

extern "C" __declspec(dllexport) const char* VR_GetVRInitErrorAsSymbol(vr::EVRInitError error) {
    return "";
}

extern "C" __declspec(dllexport) const char* VR_GetVRInitErrorAsEnglishDescription(vr::EVRInitError error) {
    return "";
}

extern "C" __declspec(dllexport) uint32_t VR_GetInitToken() {
    return 1;
}

extern "C" __declspec(dllexport) void* VRControlPanel() { return nullptr; }
extern "C" __declspec(dllexport) bool VR_GetRuntimePath(char *pchPathBuffer, uint32_t unBufferSize, uint32_t *punRequiredBufferSize) { 
    if (punRequiredBufferSize) *punRequiredBufferSize = 1; 
    if (pchPathBuffer && unBufferSize > 0) pchPathBuffer[0] = ' '; 
    return true; 
}
extern "C" __declspec(dllexport) const char* VR_GetStringForHmdError(vr::EVRInitError error) { return ""; }
extern "C" __declspec(dllexport) uint32_t VR_InitInternal(vr::EVRInitError *peError, vr::EVRApplicationType eType) {
    if (peError) *peError = vr::VRInitError_None;
    InitSharedMemory();
    return 1;
}
extern "C" __declspec(dllexport) bool VR_IsInterfaceVersionValid(const char *pchInterfaceVersion) { return true; }
extern "C" __declspec(dllexport) bool VR_IsRuntimeInstalled() { return true; }

