using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace KKMaps.Capture
{
    /// <summary>Just enough JSON for the request and result files: objects are Dictionary&lt;string, object&gt;,
    /// arrays List&lt;object&gt;, numbers double, plus string, bool and null.</summary>
    internal static class Json
    {
        public static object Parse(string text)
        {
            int i = 0;
            object value = Value(text, ref i);
            Skip(text, ref i);
            if (i != text.Length) throw new FormatException("Trailing characters at " + i);
            return value;
        }

        private static void Skip(string s, ref int i)
        {
            while (i < s.Length && char.IsWhiteSpace(s[i])) i++;
        }

        private static object Value(string s, ref int i)
        {
            Skip(s, ref i);
            if (i >= s.Length) throw new FormatException("Unexpected end");
            char c = s[i];
            if (c == '{')
            {
                var o = new Dictionary<string, object>();
                i++; Skip(s, ref i);
                if (s[i] == '}') { i++; return o; }
                while (true)
                {
                    Skip(s, ref i);
                    string key = Str(s, ref i);
                    Skip(s, ref i);
                    if (s[i++] != ':') throw new FormatException("Expected : at " + i);
                    o[key] = Value(s, ref i);
                    Skip(s, ref i);
                    char d = s[i++];
                    if (d == '}') return o;
                    if (d != ',') throw new FormatException("Expected , at " + i);
                }
            }
            if (c == '[')
            {
                var a = new List<object>();
                i++; Skip(s, ref i);
                if (s[i] == ']') { i++; return a; }
                while (true)
                {
                    a.Add(Value(s, ref i));
                    Skip(s, ref i);
                    char d = s[i++];
                    if (d == ']') return a;
                    if (d != ',') throw new FormatException("Expected , at " + i);
                }
            }
            if (c == '"') return Str(s, ref i);
            if (s.Substring(i).StartsWith("true")) { i += 4; return true; }
            if (s.Substring(i).StartsWith("false")) { i += 5; return false; }
            if (s.Substring(i).StartsWith("null")) { i += 4; return null; }
            int start = i;
            while (i < s.Length && "+-0123456789.eE".IndexOf(s[i]) >= 0) i++;
            return double.Parse(s.Substring(start, i - start), CultureInfo.InvariantCulture);
        }

        private static string Str(string s, ref int i)
        {
            if (s[i] != '"') throw new FormatException("Expected a string at " + i);
            var b = new StringBuilder();
            i++;
            while (s[i] != '"')
            {
                char c = s[i++];
                if (c != '\\') { b.Append(c); continue; }
                char e = s[i++];
                switch (e)
                {
                    case 'n': b.Append('\n'); break;
                    case 't': b.Append('\t'); break;
                    case 'r': b.Append('\r'); break;
                    case 'b': b.Append('\b'); break;
                    case 'f': b.Append('\f'); break;
                    case 'u': b.Append((char)Convert.ToInt32(s.Substring(i, 4), 16)); i += 4; break;
                    default: b.Append(e); break;
                }
            }
            i++;
            return b.ToString();
        }

        public static string Write(object value)
        {
            var b = new StringBuilder();
            Write(b, value, 0);
            b.Append('\n');
            return b.ToString();
        }

        private static void Write(StringBuilder b, object v, int indent)
        {
            string pad = new string(' ', 2 * (indent + 1));
            if (v == null) b.Append("null");
            else if (v is bool) b.Append((bool)v ? "true" : "false");
            else if (v is string) Quote(b, (string)v);
            else if (v is double || v is float || v is int || v is long)
            {
                double d = Convert.ToDouble(v, CultureInfo.InvariantCulture);
                if (double.IsNaN(d) || double.IsInfinity(d)) b.Append("null");
                else b.Append(d.ToString("R", CultureInfo.InvariantCulture));
            }
            else if (v is IDictionary<string, object>)
            {
                var o = (IDictionary<string, object>)v;
                if (o.Count == 0) { b.Append("{}"); return; }
                b.Append("{\n");
                int n = 0;
                foreach (var kv in o)
                {
                    b.Append(pad); Quote(b, kv.Key); b.Append(": ");
                    Write(b, kv.Value, indent + 1);
                    if (++n < o.Count) b.Append(',');
                    b.Append('\n');
                }
                b.Append(new string(' ', 2 * indent)).Append('}');
            }
            else if (v is IList<object>)
            {
                var a = (IList<object>)v;
                if (a.Count == 0) { b.Append("[]"); return; }
                bool flat = true;
                foreach (var x in a) if (x is IDictionary<string, object> || x is IList<object>) flat = false;
                b.Append(flat ? "[" : "[\n");
                for (int k = 0; k < a.Count; k++)
                {
                    if (!flat) b.Append(pad);
                    Write(b, a[k], indent + 1);
                    if (k + 1 < a.Count) b.Append(flat ? ", " : ",");
                    if (!flat) b.Append('\n');
                }
                if (!flat) b.Append(new string(' ', 2 * indent));
                b.Append(']');
            }
            else Quote(b, v.ToString());
        }

        private static void Quote(StringBuilder b, string s)
        {
            b.Append('"');
            foreach (char c in s)
            {
                if (c == '"' || c == '\\') b.Append('\\').Append(c);
                else if (c == '\n') b.Append("\\n");
                else if (c < ' ') b.Append("\\u").Append(((int)c).ToString("x4"));
                else b.Append(c);
            }
            b.Append('"');
        }
    }
}
