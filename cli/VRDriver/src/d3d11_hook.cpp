#include <windows.h>
#include <d3d11_1.h>
#include <dxgi1_2.h>
#include <d3d11_4.h>
#include <stdio.h>
#include <stdint.h>
#include <map>
#include "MinHook.h"

void LogProxy(const char* msg) {
    FILE* fp = fopen("Z:\\Users\\motonishikoudai\\Verantyx_VR_Drive\\proxy_log.txt", "a");
    if (fp) {
        fprintf(fp, "%s\n", msg);
        fclose(fp);
    }
}

std::map<IUnknown*, uintptr_t> g_LocalResourceHandles;
std::map<uintptr_t, ID3D11Resource*> g_HandleToResource;

typedef HRESULT (STDMETHODCALLTYPE *CreateTexture2D_t)(ID3D11Device*, const D3D11_TEXTURE2D_DESC*, const D3D11_SUBRESOURCE_DATA*, ID3D11Texture2D**);
typedef HRESULT (STDMETHODCALLTYPE *CreateBuffer_t)(ID3D11Device*, const D3D11_BUFFER_DESC*, const D3D11_SUBRESOURCE_DATA*, ID3D11Buffer**);
typedef HRESULT (STDMETHODCALLTYPE *OpenSharedResource_t)(ID3D11Device*, HANDLE, REFIID, void**);
typedef HRESULT (STDMETHODCALLTYPE *OpenSharedResource1_t)(ID3D11Device1*, HANDLE, REFIID, void**);
typedef HRESULT (STDMETHODCALLTYPE *GetSharedHandle_t)(IDXGIResource*, HANDLE*);

CreateTexture2D_t g_pOriginalCreateTexture2D = NULL;
CreateBuffer_t g_pOriginalCreateBuffer = NULL;
OpenSharedResource_t g_pOriginalOpenSharedResource = NULL;
OpenSharedResource1_t g_pOriginalOpenSharedResource1 = NULL;
GetSharedHandle_t g_pOriginalGetSharedHandle = NULL;

IUnknown* GetCanonicalIUnknown(IUnknown* pObj) {
    IUnknown* pUnk = nullptr;
    if (SUCCEEDED(pObj->QueryInterface(__uuidof(IUnknown), (void**)&pUnk))) {
        pUnk->Release();
        return pUnk;
    }
    return pObj;
}

HRESULT STDMETHODCALLTYPE Hooked_GetSharedHandle(IDXGIResource* pThis, HANDLE *pSharedHandle) {
    IUnknown* pUnk = GetCanonicalIUnknown(pThis);
    if (g_LocalResourceHandles.find(pUnk) != g_LocalResourceHandles.end()) {
        *pSharedHandle = (HANDLE)g_LocalResourceHandles[pUnk];
        return S_OK;
    }
    return g_pOriginalGetSharedHandle(pThis, pSharedHandle);
}

HRESULT STDMETHODCALLTYPE Hooked_CreateTexture2D(ID3D11Device* pDevice, const D3D11_TEXTURE2D_DESC* pDesc, const D3D11_SUBRESOURCE_DATA* pInitialData, ID3D11Texture2D** ppTexture2D) {
    if (pDesc && (pDesc->MiscFlags & (D3D11_RESOURCE_MISC_SHARED | D3D11_RESOURCE_MISC_SHARED_KEYEDMUTEX | D3D11_RESOURCE_MISC_SHARED_NTHANDLE))) {
        D3D11_TEXTURE2D_DESC newDesc = *pDesc;
        newDesc.MiscFlags &= ~(D3D11_RESOURCE_MISC_SHARED | D3D11_RESOURCE_MISC_SHARED_KEYEDMUTEX | D3D11_RESOURCE_MISC_SHARED_NTHANDLE);
        HRESULT hr = g_pOriginalCreateTexture2D(pDevice, &newDesc, pInitialData, ppTexture2D);
        if (SUCCEEDED(hr) && ppTexture2D && *ppTexture2D) {
            static uint32_t fakeHandleCounter = 0;
            fakeHandleCounter++;
            uintptr_t fakeHandle = 0xBEEF0000 | (fakeHandleCounter & 0xFFFF);
            IUnknown* pUnk = GetCanonicalIUnknown(*ppTexture2D);
            g_LocalResourceHandles[pUnk] = fakeHandle;
            g_HandleToResource[fakeHandle] = *ppTexture2D;
            
            // Log for debugging texture extraction
            char logMsg[256];
            sprintf(logMsg, "[Verantyx] Hooked_CreateTexture2D (Shared Stripped): fake handle %p, size %dx%d", (void*)fakeHandle, newDesc.Width, newDesc.Height);
            LogProxy(logMsg);
        }
        return hr;
    }
    return g_pOriginalCreateTexture2D(pDevice, pDesc, pInitialData, ppTexture2D);
}

HRESULT STDMETHODCALLTYPE Hooked_CreateBuffer(ID3D11Device* pDevice, const D3D11_BUFFER_DESC* pDesc, const D3D11_SUBRESOURCE_DATA* pInitialData, ID3D11Buffer** ppBuffer) {
    if (pDesc && (pDesc->MiscFlags & (D3D11_RESOURCE_MISC_SHARED | D3D11_RESOURCE_MISC_SHARED_KEYEDMUTEX | D3D11_RESOURCE_MISC_SHARED_NTHANDLE))) {
        D3D11_BUFFER_DESC newDesc = *pDesc;
        newDesc.MiscFlags &= ~(D3D11_RESOURCE_MISC_SHARED | D3D11_RESOURCE_MISC_SHARED_KEYEDMUTEX | D3D11_RESOURCE_MISC_SHARED_NTHANDLE);
        HRESULT hr = g_pOriginalCreateBuffer(pDevice, &newDesc, pInitialData, ppBuffer);
        if (SUCCEEDED(hr) && ppBuffer && *ppBuffer) {
            uintptr_t fakeHandle = 0xDEAD0000 | (newDesc.ByteWidth & 0xFFFF);
            IUnknown* pUnk = GetCanonicalIUnknown(*ppBuffer);
            g_LocalResourceHandles[pUnk] = fakeHandle;
            g_HandleToResource[fakeHandle] = *ppBuffer;
        }
        return hr;
    }
    return g_pOriginalCreateBuffer(pDevice, pDesc, pInitialData, ppBuffer);
}

HRESULT HandleFakeOpenSharedResource(ID3D11Device* pDevice, HANDLE hResource, REFIID ReturnedInterface, void **ppResource) {
    uintptr_t handleVal = (uintptr_t)hResource;
    if (g_HandleToResource.find(handleVal) != g_HandleToResource.end()) {
        return g_HandleToResource[handleVal]->QueryInterface(ReturnedInterface, ppResource);
    }
    return E_INVALIDARG;
}

HRESULT STDMETHODCALLTYPE Hooked_OpenSharedResource(ID3D11Device* pDevice, HANDLE hResource, REFIID ReturnedInterface, void **ppResource) {
    if (((uintptr_t)hResource & 0xFFFF0000) == 0xDEAD0000 || ((uintptr_t)hResource & 0xFFFF0000) == 0xBEEF0000) {
        return HandleFakeOpenSharedResource(pDevice, hResource, ReturnedInterface, ppResource);
    }
    return g_pOriginalOpenSharedResource(pDevice, hResource, ReturnedInterface, ppResource);
}

HRESULT STDMETHODCALLTYPE Hooked_OpenSharedResource1(ID3D11Device1* pDevice, HANDLE hResource, REFIID ReturnedInterface, void **ppResource) {
    if (((uintptr_t)hResource & 0xFFFF0000) == 0xDEAD0000 || ((uintptr_t)hResource & 0xFFFF0000) == 0xBEEF0000) {
        return HandleFakeOpenSharedResource(pDevice, hResource, ReturnedInterface, ppResource);
    }
    return g_pOriginalOpenSharedResource1(pDevice, hResource, ReturnedInterface, ppResource);
}

void ReplaceVTableEntry(void** vtable, int index, void* hook, void** original) {
    DWORD oldProtect;
    VirtualProtect(&vtable[index], sizeof(void*), PAGE_EXECUTE_READWRITE, &oldProtect);
    if (!*original) *original = vtable[index];
    vtable[index] = hook;
    VirtualProtect(&vtable[index], sizeof(void*), oldProtect, &oldProtect);
}

void SetupHooks(ID3D11Device* pDevice) {
    static bool s_hooksInstalled = false;
    if (s_hooksInstalled) return;
    s_hooksInstalled = true;
    LogProxy("[Verantyx] Setting up VTable overrides to strip shared handles...");
    
    void** pDeviceVTable = *(void***)pDevice;
    ReplaceVTableEntry(pDeviceVTable, 5, (void*)Hooked_CreateTexture2D, (void**)&g_pOriginalCreateTexture2D);
    ReplaceVTableEntry(pDeviceVTable, 3, (void*)Hooked_CreateBuffer, (void**)&g_pOriginalCreateBuffer);
    ReplaceVTableEntry(pDeviceVTable, 28, (void*)Hooked_OpenSharedResource, (void**)&g_pOriginalOpenSharedResource);
    
    ID3D11Device1* pDevice1 = nullptr;
    if (SUCCEEDED(pDevice->QueryInterface(__uuidof(ID3D11Device1), (void**)&pDevice1))) {
        void** pDevice1VTable = *(void***)pDevice1;
        ReplaceVTableEntry(pDevice1VTable, 48, (void*)Hooked_OpenSharedResource1, (void**)&g_pOriginalOpenSharedResource1);
        pDevice1->Release();
    }
    
    D3D11_TEXTURE2D_DESC desc = {};
    desc.Width = 1; desc.Height = 1; desc.MipLevels = 1; desc.ArraySize = 1;
    desc.Format = DXGI_FORMAT_R8G8B8A8_UNORM; desc.SampleDesc.Count = 1;
    desc.Usage = D3D11_USAGE_DEFAULT; desc.BindFlags = D3D11_BIND_SHADER_RESOURCE;
    ID3D11Texture2D* pTex = nullptr;
    if (SUCCEEDED(pDevice->CreateTexture2D(&desc, nullptr, &pTex))) {
        IDXGIResource* pRes = nullptr;
        if (SUCCEEDED(pTex->QueryInterface(__uuidof(IDXGIResource), (void**)&pRes))) {
            void** pResVTable = *(void***)pRes;
            ReplaceVTableEntry(pResVTable, 8, (void*)Hooked_GetSharedHandle, (void**)&g_pOriginalGetSharedHandle);
            pRes->Release();
        }
        pTex->Release();
    }
}

typedef HRESULT (WINAPI *PFN_D3D11_CREATE_DEVICE)(IDXGIAdapter*, D3D_DRIVER_TYPE, HMODULE, UINT, const D3D_FEATURE_LEVEL*, UINT, UINT, ID3D11Device**, D3D_FEATURE_LEVEL*, ID3D11DeviceContext**);
typedef HRESULT (WINAPI *PFN_D3D11_CREATE_DEVICE_AND_SWAP_CHAIN)(IDXGIAdapter*, D3D_DRIVER_TYPE, HMODULE, UINT, const D3D_FEATURE_LEVEL*, UINT, UINT, const DXGI_SWAP_CHAIN_DESC*, IDXGISwapChain**, ID3D11Device**, D3D_FEATURE_LEVEL*, ID3D11DeviceContext**);

PFN_D3D11_CREATE_DEVICE g_pOriginalD3D11CreateDevice = NULL;
PFN_D3D11_CREATE_DEVICE_AND_SWAP_CHAIN g_pOriginalD3D11CreateDeviceAndSwapChain = NULL;

HRESULT STDMETHODCALLTYPE Hooked_D3D11CreateDevice(IDXGIAdapter* pAdapter, D3D_DRIVER_TYPE DriverType, HMODULE Software, UINT Flags, const D3D_FEATURE_LEVEL* pFeatureLevels, UINT FeatureLevels, UINT SDKVersion, ID3D11Device** ppDevice, D3D_FEATURE_LEVEL* pFeatureLevel, ID3D11DeviceContext** ppImmediateContext) {
    // IMPORTANT: PASS ALL PARAMETERS UNTOUCHED TO D3DMETAL!
    HRESULT hr = g_pOriginalD3D11CreateDevice(pAdapter, DriverType, Software, Flags, pFeatureLevels, FeatureLevels, SDKVersion, ppDevice, pFeatureLevel, ppImmediateContext);
    if (SUCCEEDED(hr) && ppDevice && *ppDevice) {
        SetupHooks(*ppDevice);
        ID3D11Multithread* pMt = nullptr;
        if (SUCCEEDED((*ppDevice)->QueryInterface(__uuidof(ID3D11Multithread), (void**)&pMt))) {
            pMt->SetMultithreadProtected(TRUE);
            pMt->Release();
        }
    }
    
    char logMsg[256];
    sprintf(logMsg, "[Verantyx] D3D11CreateDevice native return: %lx", hr);
    LogProxy(logMsg);
    
    return hr;
}

HRESULT STDMETHODCALLTYPE Hooked_D3D11CreateDeviceAndSwapChain(IDXGIAdapter* pAdapter, D3D_DRIVER_TYPE DriverType, HMODULE Software, UINT Flags, const D3D_FEATURE_LEVEL* pFeatureLevels, UINT FeatureLevels, UINT SDKVersion, const DXGI_SWAP_CHAIN_DESC* pSwapChainDesc, IDXGISwapChain** ppSwapChain, ID3D11Device** ppDevice, D3D_FEATURE_LEVEL* pFeatureLevel, ID3D11DeviceContext** ppImmediateContext) {
    // IMPORTANT: PASS ALL PARAMETERS UNTOUCHED TO D3DMETAL!
    HRESULT hr = g_pOriginalD3D11CreateDeviceAndSwapChain(pAdapter, DriverType, Software, Flags, pFeatureLevels, FeatureLevels, SDKVersion, pSwapChainDesc, ppSwapChain, ppDevice, pFeatureLevel, ppImmediateContext);
    if (SUCCEEDED(hr) && ppDevice && *ppDevice) {
        SetupHooks(*ppDevice);
        ID3D11Multithread* pMt = nullptr;
        if (SUCCEEDED((*ppDevice)->QueryInterface(__uuidof(ID3D11Multithread), (void**)&pMt))) {
            pMt->SetMultithreadProtected(TRUE);
            pMt->Release();
        }
    }
    
    char logMsg[256];
    sprintf(logMsg, "[Verantyx] D3D11CreateDeviceAndSwapChain native return: %lx", hr);
    LogProxy(logMsg);
    
    return hr;
}

void InitHook() {
    static bool bInit = false;
    if (bInit) return;
    bInit = true;
    
    char exePath[MAX_PATH] = {0};
    GetModuleFileNameA(NULL, exePath, MAX_PATH);
    LogProxy("[Verantyx] D3D11 Hook Initializing in:");
    LogProxy(exePath);
    
    MH_Initialize();
    
    char sysDir[MAX_PATH];
    GetSystemDirectoryA(sysDir, MAX_PATH);
    strcat(sysDir, "\\d3d11.dll");
    
    HMODULE hD3D11 = LoadLibraryExA(sysDir, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (hD3D11) {
        void* pD3D11CreateDevice = (void*)GetProcAddress(hD3D11, "D3D11CreateDevice");
        void* pD3D11CreateDeviceAndSwapChain = (void*)GetProcAddress(hD3D11, "D3D11CreateDeviceAndSwapChain");
        if (pD3D11CreateDevice) MH_CreateHook(pD3D11CreateDevice, (void*)Hooked_D3D11CreateDevice, (LPVOID*)&g_pOriginalD3D11CreateDevice);
        if (pD3D11CreateDeviceAndSwapChain) MH_CreateHook(pD3D11CreateDeviceAndSwapChain, (void*)Hooked_D3D11CreateDeviceAndSwapChain, (LPVOID*)&g_pOriginalD3D11CreateDeviceAndSwapChain);
        MH_EnableHook(MH_ALL_HOOKS);
        LogProxy("[Verantyx] Successfully hooked D3DMetal natively.");
    } else {
        LogProxy("[Verantyx] FAILED to load system d3d11.dll!");
    }
}

extern "C" __declspec(dllexport) HRESULT WINAPI D3D11CreateDevice(IDXGIAdapter* pAdapter, D3D_DRIVER_TYPE DriverType, HMODULE Software, UINT Flags, const D3D_FEATURE_LEVEL* pFeatureLevels, UINT FeatureLevels, UINT SDKVersion, ID3D11Device** ppDevice, D3D_FEATURE_LEVEL* pFeatureLevel, ID3D11DeviceContext** ppImmediateContext) {
    InitHook();
    if (g_pOriginalD3D11CreateDevice) return Hooked_D3D11CreateDevice(pAdapter, DriverType, Software, Flags, pFeatureLevels, FeatureLevels, SDKVersion, ppDevice, pFeatureLevel, ppImmediateContext);
    return E_FAIL;
}

extern "C" __declspec(dllexport) HRESULT WINAPI D3D11CreateDeviceAndSwapChain(IDXGIAdapter* pAdapter, D3D_DRIVER_TYPE DriverType, HMODULE Software, UINT Flags, const D3D_FEATURE_LEVEL* pFeatureLevels, UINT FeatureLevels, UINT SDKVersion, const DXGI_SWAP_CHAIN_DESC* pSwapChainDesc, IDXGISwapChain** ppSwapChain, ID3D11Device** ppDevice, D3D_FEATURE_LEVEL* pFeatureLevel, ID3D11DeviceContext** ppImmediateContext) {
    InitHook();
    if (g_pOriginalD3D11CreateDeviceAndSwapChain) return Hooked_D3D11CreateDeviceAndSwapChain(pAdapter, DriverType, Software, Flags, pFeatureLevels, FeatureLevels, SDKVersion, pSwapChainDesc, ppSwapChain, ppDevice, pFeatureLevel, ppImmediateContext);
    return E_FAIL;
}
