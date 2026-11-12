// A 360 photo as the whole world: its sky all around, and its own ground
// (sand, water, rocks) projected onto the floor under the user, so they
// stand inside the photo instead of on a flat floor in front of it. Moving
// a few metres shifts the ground naturally; far from the middle it stretches.
//
// The photo is assumed taken from Camera Height above the floor at the
// world's origin. Within Radius the view lands on the floor; beyond it, on
// a dome. Rotation turns the photo the same way as Skybox/Panoramic.
//
// Used as the scene's skybox (Window > Rendering > Lighting > Skybox
// Material); XRPodSceneBuilder sets it up for each photo world.

Shader "XRPod/Ground Projected Skybox"
{
    Properties
    {
        [NoScaleOffset] _MainTex ("360 photo (latitude-longitude)", 2D) = "grey" {}
        _Rotation ("Rotation", Range(0, 360)) = 0
        _Exposure ("Exposure", Range(0, 4)) = 1
        _CameraHeight ("Photo camera height (m)", Float) = 1.7
        _Radius ("Ground radius (m)", Float) = 60
    }

    SubShader
    {
        Tags { "Queue" = "Background" "RenderType" = "Background" "PreviewType" = "Skybox" "RenderPipeline" = "UniversalPipeline" }
        Cull Off
        ZWrite Off

        Pass
        {
            HLSLPROGRAM
            #pragma vertex Vert
            #pragma fragment Frag
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.core/ShaderLibrary/Common.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            TEXTURE2D(_MainTex);
            SAMPLER(sampler_MainTex);

            CBUFFER_START(UnityPerMaterial)
                float _Rotation;
                float _Exposure;
                float _CameraHeight;
                float _Radius;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 direction : TEXCOORD0; // the skybox mesh is a sphere of directions
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings Vert(Attributes input)
            {
                Varyings output;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                output.direction = input.positionOS.xyz;
                return output;
            }

            // Same turn as Skybox/Panoramic's Rotation.
            float3 RotateY(float3 d, float degrees)
            {
                float a = degrees * PI / 180.0;
                float s = sin(a);
                float c = cos(a);
                return float3(c * d.x - s * d.z, d.y, s * d.x + c * d.z);
            }

            half4 Frag(Varyings input) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);
                float3 d = normalize(input.direction);
                float3 eye = GetCameraPositionWS();
                float3 photo = float3(0.0, _CameraHeight, 0.0); // where the photo was taken

                // Where the view ray lands: the floor (y = 0) if that's within
                // the radius, otherwise a dome around the photo's spot.
                float3 hit;
                float tFloor = d.y < -1e-4 ? -eye.y / d.y : 1e9;
                float3 onFloor = eye + d * tFloor;
                if (tFloor < 1e8 && dot(onFloor.xz, onFloor.xz) < _Radius * _Radius)
                {
                    hit = onFloor;
                }
                else
                {
                    float3 fromPhoto = eye - photo;
                    float b = dot(fromPhoto, d);
                    float c = dot(fromPhoto, fromPhoto) - _Radius * _Radius;
                    hit = eye + d * (-b + sqrt(max(b * b - c, 0.0)));
                }

                // Look that point up in the photo, seen from where it was taken.
                float3 dir = RotateY(normalize(hit - photo), _Rotation);
                float2 uv = float2(0.5 - atan2(dir.z, dir.x) * (0.5 / PI), 1.0 - acos(clamp(dir.y, -1.0, 1.0)) / PI);
                half3 color = SAMPLE_TEXTURE2D_LOD(_MainTex, sampler_MainTex, uv, 0).rgb;
                return half4(color * _Exposure, 1.0);
            }
            ENDHLSL
        }
    }

    Fallback Off
}
