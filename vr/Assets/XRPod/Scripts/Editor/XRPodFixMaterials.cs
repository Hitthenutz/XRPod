// Fixes pink (unsupported) materials from older store packs that Unity's
// Render Pipeline Converter can't handle, e.g. leaves using a pack's own
// "StandardNoCulling" shader. Each one is switched to URP Lit with its
// texture, colour and normal map kept, cut-out edges (leaves) and both
// sides drawn. Only touches materials in the folder you pick.

using System.Collections.Generic;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace XRPod.VR
{
    static class XRPodFixMaterials
    {
        [MenuItem("XRPod/Fix Pink Materials (selected folder)")]
        static void FixSelectedFolder()
        {
            var folder = PickedFolder();
            if (folder == null || folder == "Assets" || folder.StartsWith("Assets/XRPod"))
            {
                EditorUtility.DisplayDialog("Fix Pink Materials",
                    "In the Project window, click the pack's folder first " +
                    "(e.g. Assets > Fantasy Forest Environment Free Sample), then run this again.", "OK");
                return;
            }

            var fixedNames = FixFolder(folder);
            if (fixedNames == null)
            {
                EditorUtility.DisplayDialog("Fix Pink Materials", "Couldn't find URP's Lit shader.", "OK");
                return;
            }
            EditorUtility.DisplayDialog("Fix Pink Materials",
                fixedNames.Count == 0
                    ? "Nothing to fix in " + folder + ": no pink materials found."
                    : $"Fixed {fixedNames.Count} material(s):\n" + string.Join(", ", fixedNames),
                "OK");
        }

        // Fixes every pink material in `folder` (e.g. a store pack's).
        // Returns the names of the ones changed, or null without URP's Lit.
        internal static List<string> FixFolder(string folder)
        {
            var lit = Shader.Find("Universal Render Pipeline/Lit");
            if (lit == null) return null;

            var fixedNames = new List<string>();
            foreach (var guid in AssetDatabase.FindAssets("t:Material", new[] { folder }))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
                if (mat == null) continue;
                if (IsInvisibleLit(mat))
                {
                    // Fixed by an earlier version of this tool: make it solid.
                    Undo.RecordObject(mat, "Fix pink materials");
                    var c = mat.GetColor("_BaseColor");
                    c.a = 1f;
                    mat.SetColor("_BaseColor", c);
                    EditorUtility.SetDirty(mat);
                    fixedNames.Add(mat.name);
                    continue;
                }
                if (!NeedsFix(mat)) continue;
                Undo.RecordObject(mat, "Fix pink materials");
                ToLit(mat, lit);
                EditorUtility.SetDirty(mat);
                fixedNames.Add(mat.name);
            }
            AssetDatabase.SaveAssets();
            return fixedNames;
        }

        // The selected folder (or the folder of a selected file), else the
        // folder the Project window is showing.
        static string PickedFolder()
        {
            var path = AssetDatabase.GetAssetPath(Selection.activeObject);
            if (!string.IsNullOrEmpty(path))
                return AssetDatabase.IsValidFolder(path) ? path : System.IO.Path.GetDirectoryName(path)?.Replace('\\', '/');
            // Unity has no public call for this; it's been internal for years.
            var method = typeof(ProjectWindowUtil).GetMethod("GetActiveFolderPath",
                System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic);
            return method?.Invoke(null, null) as string;
        }

        // A URP Lit cut-out material whose colour has zero opacity: every
        // pixel is cut away, so it can't be seen at all.
        static bool IsInvisibleLit(Material mat) =>
            mat.shader != null && mat.shader.name == "Universal Render Pipeline/Lit"
            && mat.HasProperty("_AlphaClip") && mat.GetFloat("_AlphaClip") > 0.5f
            && mat.GetColor("_BaseColor").a < 0.01f;

        // Pink = the shader is broken or isn't a URP shader. Skyboxes are
        // left alone (each v1 world gets its own sky).
        static bool NeedsFix(Material mat)
        {
            var shader = mat.shader;
            if (shader == null || !shader.isSupported || shader.name == "Hidden/InternalErrorShader") return true;
            var name = shader.name;
            if (name.StartsWith("Skybox/")) return false;
            return !(name.StartsWith("Universal Render Pipeline/") || name.StartsWith("Shader Graphs/")
                     || name.StartsWith("XRPod/") || name.StartsWith("Sprites/") || name.StartsWith("UI/")
                     || name.StartsWith("Hidden/") || name.StartsWith("TextMeshPro/"));
        }

        static void ToLit(Material mat, Shader lit)
        {
            // Read the old values before switching (URP uses other names).
            var tex = Tex(mat, "_MainTex");
            var color = mat.HasProperty("_Color") ? mat.GetColor("_Color") : Color.white;
            // Old shaders often ignore the colour's alpha (some packs leave it
            // at 0); URP multiplies by it, which would make the whole thing
            // invisible. See-through parts come from the texture instead.
            color.a = 1f;
            var normal = Tex(mat, "_BumpMap");
            var cutoff = mat.HasProperty("_Cutoff") ? mat.GetFloat("_Cutoff") : 0.5f;
            var scale = mat.HasProperty("_MainTex") ? mat.GetTextureScale("_MainTex") : Vector2.one;
            var offset = mat.HasProperty("_MainTex") ? mat.GetTextureOffset("_MainTex") : Vector2.zero;
            // Leaves and grass: textures with see-through parts.
            var cutOut = tex is Texture2D t2 && GraphicsFormatHasAlpha(t2);

            mat.shader = lit;
            mat.SetTexture("_BaseMap", tex);
            mat.SetTextureScale("_BaseMap", scale);
            mat.SetTextureOffset("_BaseMap", offset);
            mat.SetColor("_BaseColor", color);
            mat.SetFloat("_Smoothness", 0.1f);
            mat.SetFloat("_Surface", 0f); // opaque

            if (normal != null)
            {
                mat.SetTexture("_BumpMap", normal);
                mat.EnableKeyword("_NORMALMAP");
            }

            mat.SetFloat("_AlphaClip", cutOut ? 1f : 0f);
            mat.SetFloat("_Cutoff", cutoff);
            if (cutOut)
            {
                mat.EnableKeyword("_ALPHATEST_ON");
                mat.SetOverrideTag("RenderType", "TransparentCutout");
                mat.renderQueue = (int)RenderQueue.AlphaTest;
            }
            else
            {
                mat.DisableKeyword("_ALPHATEST_ON");
                mat.SetOverrideTag("RenderType", "Opaque");
                mat.renderQueue = (int)RenderQueue.Geometry;
            }

            // Draw both sides, like the old "NoCulling" shader (leaves are flat cards).
            mat.SetFloat("_Cull", (float)CullMode.Off);
            mat.doubleSidedGI = true;
        }

        static Texture Tex(Material mat, string property) =>
            mat.HasProperty(property) ? mat.GetTexture(property) : null;

        static bool GraphicsFormatHasAlpha(Texture2D tex) =>
            UnityEngine.Experimental.Rendering.GraphicsFormatUtility.HasAlphaChannel(tex.graphicsFormat);
    }
}
